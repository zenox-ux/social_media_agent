
import os
import re
import json
import time
import random
import uuid
from io import BytesIO
from typing import TypedDict, Optional, List, Dict, Any, Tuple

# --- Third-Party Libraries ---
import bcrypt
import google.generativeai as genai
import praw
import requests
import streamlit as st
import tweepy
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from PIL import Image
from supabase import create_client, Client


from src.config import (
    OPENAI_API_KEY, FIRE_CRAWL_API_KEY, GEMINI_API_KEY,
    TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_SUBREDDIT,
    SUPABASE_URL, SUPABASE_KEY
)



def post_to_reddit(title: str, body: str, image_path: Optional[str] = None) -> str:
    reddit = praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent='FaiqQazi Reddit Bot',
        username=os.getenv('REDDIT_USER_NAME'),
        password=os.getenv('REDDIT_PASSWORD')
    )

    subreddit_name = os.getenv("REDDIT_SUBREDDIT", "test")
    subreddit = reddit.subreddit(subreddit_name)

    print(f"🟠 Posting to r/{subreddit_name}...")

    if image_path:
        try:
            # Verify image exists and is accessible
            if not os.path.exists(image_path):
                print(f"⚠️ Image file not found: {image_path}")
                raise FileNotFoundError(f"Image file not found: {image_path}")

            # Verify image can be opened and is valid
            try:
                with Image.open(image_path) as img:
                    # Check if image is valid
                    img.verify()
                    print("✅ Image verified successfully")
            except Exception as e:
                print(f"⚠️ Invalid image file: {e}")
                raise ValueError(f"Invalid image file: {e}")

            # Try to submit image post
            try:
                submission = subreddit.submit_image(title=title, image_path=image_path)
                print("📝 Posting body as a comment...")
                submission.reply(body)
            except Exception as e:
                print(f"⚠️ Failed to submit image post, falling back to text post: {e}")
                # Fallback to text post if image submission fails
                submission = subreddit.submit(title=title, selftext=f"{body}\n\n[Image submission failed]")
        except Exception as e:
            print(f"⚠️ Image post failed, submitting as text post: {e}")
            submission = subreddit.submit(title=title, selftext=body)
    else:
        # Submit text post
        submission = subreddit.submit(title=title, selftext=body)

    return submission.url





def search_and_filter_posts(reddit, subreddits: list[str], topic: str, search_limit_per_sub: int = 50) -> tuple[list, list, list]:
    """
    Searches for posts and comments, scores them, and returns three distinct lists:
    1. Top overall submissions (PRAW objects)
    2. Top individual posts (title/body text, as dicts)
    3. Top individual comments (PRAW comment objects)
    """
    print(f"\n🚀 --- Advanced Reddit Search & Filter ---")
    print(f"🔍 Topic: '{topic}' | Searching across {len(subreddits)} subreddits | Limit per subreddit: {search_limit_per_sub}")
    if not subreddits:
        print("❌ No subreddits provided for search. Exiting.")
        return [], [], []
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD
    )
    # --- Stage 1: Keyword Expansion ---
    print("\n📚 Stage 1: Expanding topic into relevant keywords using LLM...")
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.2, openai_api_key=OPENAI_API_KEY)
    keyword_expansion_prompt = f"""You are a search query expert. For the given topic, generate a list of highly relevant keywords and phrases.
You can give phrases but prefer keywords (~2/3) over phrases (~1/3).
Topic: "{topic}"
"""
    try:
        response = llm.invoke(keyword_expansion_prompt)
        keywords = {kw.strip().lower() for kw in response.content.split(',') if kw.strip()}
        keywords.update({word.lower() for word in topic.split()})
        print(f"✅ Keywords generated: {len(keywords)}")
        print("🧠 Example keywords:", list(keywords)[:10])
    except Exception as e:
        print(f"⚠️ LLM keyword expansion failed: {e}. Falling back to topic words only.")
        keywords = {word.lower() for word in topic.split()}

    # --- Stage 2: Broad Search ---
    print("\n🌐 Stage 2: Performing subreddit search...")
    all_found_submissions = []
    unique_submission_ids = set()
    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            print(f"🔎 Searching in r/{sub_name} ...")
            search_results = subreddit.search(topic, sort='relevance', time_filter='year', limit=search_limit_per_sub)
            count = 0
            for submission in search_results:
                if submission.id not in unique_submission_ids:
                    all_found_submissions.append(submission)
                    unique_submission_ids.add(submission.id)
                    count += 1
            print(f"✅ Found {count} new posts in r/{sub_name}")
        except Exception as e:
            print(f"⚠️ Error searching r/{sub_name}: {e}")

    if not all_found_submissions:
        print("❌ No posts found in any subreddit.")
        return [], [], []

    print(f"📦 Total unique posts collected: {len(all_found_submissions)}")

    # --- Stage 3: Scoring Content ---
    print("\n🧮 Stage 3: Scoring posts, post bodies, and comments...")
    scored_submissions = []
    scored_posts = []
    scored_comments = []

    for i, submission in enumerate(all_found_submissions, 1):
        print(f"\n📄 [{i}/{len(all_found_submissions)}] Processing submission ID: {submission.id}")
        try:
            title_text = submission.title.lower()
            body_text = (submission.selftext or "").lower()

            post_only_score = sum(title_text.count(kw) * 5 + body_text.count(kw) * 2 for kw in keywords)
            print(f"   📊 Title + Body Score: {post_only_score} | Post score: {submission.score}")

            if post_only_score > 0:
                scored_posts.append((post_only_score + submission.score, submission))

            submission_total_relevance = post_only_score
            try:
                submission.comments.replace_more(limit=None)
                comment_list = submission.comments.list()
                print(f"   💬 Total comments: {len(comment_list)}")
                for comment in comment_list:
                    comment_text = comment.body.lower()
                    individual_comment_score = sum(comment_text.count(kw) * 3 for kw in keywords)
                    submission_total_relevance += sum(comment_text.count(kw) for kw in keywords)

                    if individual_comment_score > 0:
                        scored_comments.append((individual_comment_score + comment.score, comment))
            except Exception as comment_error:
                print(f"   ⚠️ Failed to process comments for {submission.id}: {comment_error}")

            final_submission_score = (submission_total_relevance * 2) + submission.score
            print(f"   🧮 Final Submission Score: {final_submission_score}")
            scored_submissions.append((final_submission_score, submission))
        except Exception as sub_error:
            print(f"❌ Error processing submission ID {submission.id}: {sub_error}")
            continue

    # --- Stage 4: Selecting Top Results ---
    print("\n🏁 Stage 4: Selecting top-ranked results...")

    scored_submissions.sort(key=lambda x: x[0], reverse=True)
    top_submissions = [sub for score, sub in scored_submissions[:10]]
    print(f"✔️ Top Submissions Selected: {len(top_submissions)}")

    scored_posts.sort(key=lambda x: x[0], reverse=True)
    top_individual_posts = [sub for score, sub in scored_posts[:40]]
    print(f"✔️ Top Individual Posts Selected: {len(top_individual_posts)}")

    scored_comments.sort(key=lambda x: x[0], reverse=True)
    top_individual_comments = [comment for score, comment in scored_comments[:50]]
    print(f"✔️ Top Individual Comments Selected: {len(top_individual_comments)}")

    print("\n✅ Advanced Search & Filter completed successfully.")
    return top_submissions, top_individual_posts, top_individual_comments




def validate_subreddit(reddit, subreddit_name: str) -> bool:
    """Validates if a subreddit exists and is accessible."""
    try:
        reddit.subreddit(subreddit_name).id  # Fetch subreddit ID to confirm existence
        print(f"✅ Subreddit r/{subreddit_name} is valid and accessible")
        return True
    except (praw.exceptions.Forbidden, praw.exceptions.NotFound) as e:
        print(f"⚠️ Subreddit r/{subreddit_name} is private, banned, or does not exist: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating subreddit r/{subreddit_name}: {e}")
        return False  
    



def scrape_validated_posts(
    top_submissions: list[praw.models.Submission],
    top_posts: list[praw.models.Submission],
    top_comments: list[praw.models.Comment]
) -> list[dict]:
    """
    Takes the three validated lists and prepares a unified list of dictionaries for the report generator.
    Includes detailed logs and error tracking.
    """
    print("\n🔎 -> Starting to consolidate and scrape validated Reddit content...")
    scraped_data = []
    processed_ids = set()  # To avoid duplicating posts

    # 1. Scrape the top overall submissions (with their comments)
    print(f"\n📘 Step 1: Scraping {len(top_submissions)} top full submissions (with comments)...")
    for i, submission in enumerate(top_submissions, 1):
        print(f"  [{i}/{len(top_submissions)}] Processing submission ID: {submission.id} | Title: {submission.title[:50]}...")
        if submission.id in processed_ids:
            print("    🔁 Skipped (already processed)")
            continue

        post_data = {
            "type": "full_submission",
            "title": submission.title,
            "url": submission.url,
            "score": submission.score,
            "selftext": submission.selftext or "",
            "top_comments": []
        }

        try:
            submission.comments.replace_more(limit=0)
            top_five_comments = submission.comments.list()[:5]
            for comment in top_five_comments:
                post_data["top_comments"].append({"body": comment.body, "score": comment.score})
            print(f"    ✅ Added {len(top_five_comments)} comments to post.")
        except Exception as e:
            print(f"    ⚠️ Error fetching comments for submission ID {submission.id}: {e}")

        scraped_data.append(post_data)
        processed_ids.add(submission.id)

    # 2. Add the top individual posts
    print(f"\n📘 Step 2: Adding {len(top_posts)} individual top posts (text-only)...")
    for i, post in enumerate(top_posts, 1):
        print(f"  [{i}/{len(top_posts)}] Processing post ID: {post.id} | Title: {post.title[:50]}...")
        if post.id in processed_ids:
            print("    🔁 Skipped (already processed)")
            continue
        try:
            scraped_data.append({
                "type": "individual_post",
                "title": post.title,
                "selftext": post.selftext or "",
                "score": post.score,
            })
            processed_ids.add(post.id)
            print("    ✅ Post added successfully.")
        except Exception as e:
            print(f"    ⚠️ Error adding individual post ID {post.id}: {e}")

    # 3. Add the top individual comments
    print(f"\n📘 Step 3: Adding {len(top_comments)} top individual comments...")
    if top_comments:
        comment_nuggets = []
        for i, comment in enumerate(top_comments, 1):
            try:
                comment_nuggets.append({
                    "body": comment.body,
                    "score": comment.score
                })
                print(f"    ✅ Added comment {i}/{len(top_comments)} | Score: {comment.score}")
            except Exception as e:
                print(f"    ⚠️ Error processing comment {i}: {e}")

        scraped_data.append({
            "type": "comment_nuggets",
            "comments": comment_nuggets
        })
    else:
        print("    ⚠️ No top comments provided to add.")

    print(f"\n🎯 Consolidation complete! Total items added for reporting: {len(scraped_data)}")
    print("printing the scrapped data")
    for item in scraped_data:
        print(f"  - Type: {item['type']}, Title: {item.get('title', 'N/A')}, Comments: {len(item.get('top_comments', [])) if 'top_comments' in item else 0}")

    return scraped_data
