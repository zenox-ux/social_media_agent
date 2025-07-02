# --- Imports ---
import os
import requests
from typing import TypedDict, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import re
import json
import tweepy
import praw
import google.generativeai as genai
import random
from PIL import Image
from io import BytesIO
import time

# --- Load environment variables ---
load_dotenv()

# --- API Key Checks ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FIRE_CRAWL_API_KEY = os.getenv("FIRE_CRAWL_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY not found. Check your .env file.")

if not FIRE_CRAWL_API_KEY:
    raise ValueError("❌ FIRE_CRAWL_API_KEY not found. Check your .env file.")

# --- Type Definitions ---
class AgentState(TypedDict):
    generated_text: str
    url: Optional[str]
    scraped_content: Optional[str]

# --- Utility Functions ---

def post_to_twitter_oauth1(text: str) -> dict:
    consumer_key = os.getenv("TWITTER_CONSUMER_KEY")
    consumer_secret = os.getenv("TWITTER_CONSUMER_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")

    if not all([consumer_key, consumer_secret, access_token, access_secret]):
        raise ValueError("❌ Missing Twitter OAuth1 credentials in environment variables.")

    client = tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_secret
    )

    print("✈️ Sending tweet...")
    response = client.create_tweet(text=text)
    return response.data

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


def get_best_image_from_candidates(image_urls: list[str], post_text: str) -> Optional[str]:
    print("\n📊 Starting image selection process...")
    if not image_urls:
        print("❌ No image URLs provided")
        return None

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY not found. Skipping image validation.")
        return image_urls[0]

    print(f"\n🔍 Found {len(image_urls)} total images")
    print("Original image URLs:")
    for i, url in enumerate(image_urls, 1):
        print(f"{i}. {url}")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    if len(image_urls) > 4:
        candidate_urls = random.sample(image_urls, 4)
        print("\n🎲 Randomly selected 4 images for evaluation:")
    else:
        candidate_urls = image_urls
        print("\n📋 Using all available images for evaluation:")
    
    print("\nCandidate URLs being evaluated:")
    for i, url in enumerate(candidate_urls, 1):
        print(f"{i}. {url}")

    prompt = f"""You are an expert in matching images with content. 
You will be shown 4 images and a social media post. Your task is to determine which image is the most relevant.
Reply ONLY with the number (1-4) corresponding to the most relevant image.

Post:
\"\"\"{post_text}\"\"\"
"""

    image_parts = []
    url_map = {}
    
    print("\n⬇️ Downloading images...")
    for i, url in enumerate(candidate_urls):
        try:
            print(f"Downloading image {i+1}: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            image_data = response.content
            mime_type = response.headers.get('Content-Type', 'image/jpeg')
            print(f"✅ Successfully downloaded image {i+1} ({len(image_data)} bytes, type: {mime_type})")

            image_parts.append({"mime_type": mime_type, "data": image_data})
            url_map[str(i+1)] = url
        except Exception as e:
            print(f"⚠️ Skipping image {url}: {e}")

    if not image_parts:
        print("❌ No images were successfully downloaded")
        return None

    print(f"\n🤖 Asking Gemini to evaluate {len(image_parts)} images...")
    try:
        parts = [{"text": prompt}] + image_parts
        response = model.generate_content(parts)
        print(f"\n📝 Gemini's response: {response.text.strip()}")
        
        chosen_index = re.search(r'\b[1-4]\b', response.text.strip())
        if chosen_index:
            chosen = chosen_index.group()
            selected_url = url_map[chosen]
            print(f"\n🎯 Selected image {chosen} out of {len(image_parts)}")
            print(f"🔗 Selected URL: {selected_url}")
            return selected_url
        else:
            print("⚠️ Gemini response did not contain a valid image index.")
            return None
    except Exception as e:
        print(f"⚠️ Gemini API error: {e}")
        return None


def extract_images_from_firecrawl(response_string: str) -> list[str]:
    try:
        data = json.loads(response_string)
        markdown_content = data.get("data", {}).get("markdown", "")

        if not markdown_content:
            print("No markdown content found in the response.")
            return []

        image_pattern = r'!\[.*?\]\((.*?)\)'
        found_urls = re.findall(image_pattern, markdown_content)

        return list(dict.fromkeys(found_urls))  # Unique URLs
    except json.JSONDecodeError:
        print("Error: Invalid JSON string provided.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []
    




def scrape_and_format_content(url: str) -> tuple[str, str]:
    """
    Scrapes content from a given URL using FireCrawl's /scrape endpoint and formats it using LLM.
    """
    print(f"-> Scraping content from {url}")

    headers = {
        "Authorization": f"Bearer {FIRE_CRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "formats": ["markdown"],  # You can also include "html" if needed
        "onlyMainContent": True
    }

    response = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers=headers,
        json=payload
    )

    if not response.ok:
        raise Exception(f"Failed to scrape URL: {response.status_code} - {response.text}")

    try:
        data = response.json()
        print("🔥 Parsed FireCrawl response:", data)
    except Exception as e:
        raise ValueError(f"Invalid JSON response from FireCrawl: {e}")

    # Extract markdown content
    scraped_content = data.get("data", {}).get("markdown", "")

    if not scraped_content.strip():
        raise ValueError("Scraped content is empty.")

    print(f"<- Scraped content length: {len(scraped_content)} characters")
    print(scraped_content[:500])  # Preview content

    # Format with LLM
    llm = ChatOpenAI(
        model="gpt-4",
        temperature=0.3,
        openai_api_key=OPENAI_API_KEY
    )

    formatting_prompt = f"""You are an expert content curator and summarizer.
Below is content scraped from a webpage. Please analyze it and create a well-structured, 
fact-focused summary that:
1. Retains the most important facts and key information
2. Removes any redundant or unnecessary content
3. Maintains proper context
4. Is suitable for generating an informative social media post

Content: \"\"\"{scraped_content}\"\"\"

Format the output as a clear, concise summary that captures the essence of the content.
"""

    response = llm.invoke(formatting_prompt)
    formatted_content = response.content

    print("<- Content scraped and formatted")
    return formatted_content, json.dumps(data) 

def generate_post_function(content: str) -> tuple[str, str]:
    """
    Calls LLM to generate a social media post and title based on the given content.
    Returns a tuple of (title, post_text).
    """
    print("-> Generating social media post and title")

    llm = ChatOpenAI(
        model="gpt-4",
        temperature=0.7,
        openai_api_key=OPENAI_API_KEY
    )

    base_prompt = f"""You are a social media marketer.
Create:
1. A title (maximum 100 characters)
2. A post body (between 200 and 400 characters)

The content should be based on the following text. Make them informative, engaging, and optimized for social media.
Focus on facts and numbers and things of conceptual importance, not on specific names or brands. Avoid promotional tone.

Content: \"\"\"{content}\"\"\"

Format your response exactly like this:
TITLE: [your title here]
POST: [your post here]
"""

    response = llm.invoke(base_prompt)
    response_text = response.content.strip()
    
    # Extract title and post from response
    title_match = re.search(r'TITLE:\s*(.+?)\s*\nPOST:', response_text, re.DOTALL)
    post_match = re.search(r'POST:\s*(.+?)$', response_text, re.DOTALL)
    
    title = title_match.group(1).strip() if title_match else "AI-Powered Insights"
    post_text = post_match.group(1).strip() if post_match else response_text

    # Validate post length
    retries = 2
    while (len(post_text) < 200 or len(post_text) > 400) and retries > 0:
        print(f"⚠️ Post length = {len(post_text)} characters. Retrying...")
        retry_prompt = f"""Rewrite the following post so that it is between 200 and 400 characters long.
Avoid fluff and names, and focus on facts only.

Original Post:
\"\"\"{post_text}\"\"\"
"""
        response = llm.invoke(retry_prompt)
        post_text = response.content.strip()
        retries -= 1

    print(f"📝 Generated title: {title}")
    print(f"📄 Generated post ({len(post_text)} characters)")
    return title, post_text 
  
def find_relevant_subreddits(topic: str, limit: int = 20)->list[str]:
    """Uses an LLM to find highly relevant, niche subreddits for a given topic."""
    print(f"-> Finding relevant subreddits for topic: '{topic}'...")
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, openai_api_key=OPENAI_API_KEY)
    
    # This improved prompt asks for niche communities, which is key.
    prompt = f"""You are a Reddit search expert. For the given topic, list the best {limit} subreddits to find high-quality, specific discussions.
    Prioritize niche subreddits over massive general ones. For example, for "Canadian immigration for tech workers", prefer r/ImmigrationCanada over just r/canada.
                                                    
    Do not include the "r/" prefix. Respond with a comma-separated list and nothing else.
    
    Topic: "{topic}"
    """
    try:
        response = llm.invoke(prompt)
        subreddits = [s.strip() for s in response.content.split(',') if s.strip()]
        print(f"<- Found potential subreddits: {subreddits}")
        return subreddits
    except Exception as e:
        print(f"<- Failed to find subreddits: {e}")
        return []

def search_and_filter_posts(reddit, subreddits: list[str], topic: str, search_limit_per_sub: int = 25) -> tuple[list, list, list]:
    """
    Searches for posts and comments, scores them, and returns three distinct lists:
    1. Top overall submissions (PRAW objects)
    2. Top individual posts (title/body text, as dicts)
    3. Top individual comments (PRAW comment objects)
    """
    print(f"\n🚀 --- Advanced Reddit Search & Filter ---")
    print(f"🔍 Topic: '{topic}' | Searching across {len(subreddits)} subreddits | Limit per subreddit: {search_limit_per_sub}")

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
    top_submissions = [sub for score, sub in scored_submissions[:4]]
    print(f"✔️ Top Submissions Selected: {len(top_submissions)}")

    scored_posts.sort(key=lambda x: x[0], reverse=True)
    top_individual_posts = [sub for score, sub in scored_posts[:20]]
    print(f"✔️ Top Individual Posts Selected: {len(top_individual_posts)}")

    scored_comments.sort(key=lambda x: x[0], reverse=True)
    top_individual_comments = [comment for score, comment in scored_comments[:40]]
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

from math import ceil
def generate_report_from_posts(topic: str, consolidated_data: list[dict]) -> str:
    """
    Generates a structured report from the consolidated data, now handling
    different item types safely.
    """
    print("\n📝 Generating comprehensive report from consolidated Reddit data...")

    # --- Step 1: Format the consolidated data into a single, structured text block ---
    # This replaces the complex batching logic and makes the process more reliable.
    
    llm_context_text = ""
    print("-> Formatting consolidated data for the final LLM prompt...")

    for i, item in enumerate(consolidated_data):
        item_type = item.get('type', 'unknown')
        print(f"  - Formatting item {i+1}/{len(consolidated_data)} of type: '{item_type}'")

        if item_type == 'full_submission':
            llm_context_text += f"\n\n--- Full Discussion Thread ---\n"
            llm_context_text += f"Title: {item.get('title', 'N/A')}\n"
            llm_context_text += f"Post Body: {item.get('selftext', '')}\n"
            if item.get('top_comments'):
                llm_context_text += "Top Comments:\n"
                for c in item['top_comments']:
                    llm_context_text += f"- (Score: {c.get('score', 0)}) {c.get('body', '')}\n"
        
        elif item_type == 'individual_post':
            llm_context_text += f"\n\n--- Relevant Post (Text Only) ---\n"
            llm_context_text += f"Title: {item.get('title', 'N/A')}\n"
            llm_context_text += f"Post Body: {item.get('selftext', '')}\n"
            
        elif item_type == 'comment_nuggets':
            llm_context_text += f"\n\n--- Highly Relevant Individual Comments (from various threads) ---\n"
            if item.get('comments'):
                for c in item['comments']:
                    llm_context_text += f"- (Score: {c.get('score', 0)}) \"{c.get('body', '')}\"\n"
        else:
            print(f"  - ⚠️ Skipping unknown item type: {item_type}")

    if not llm_context_text.strip():
        print("⚠️ No valid data was formatted for the report. Aborting.")
        return f"# Report on {topic}\n\nNo relevant content could be processed."

    # --- Step 2: Generate the final report in a single, powerful LLM call ---
    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.2, openai_api_key=OPENAI_API_KEY)

    prompt = f"""You are a world-class research analyst. Your task is to synthesize a collection of Reddit discussions into a single, coherent report about the topic: '{topic}'.

    You have been provided with full discussion threads, individual relevant posts, and a curated list of 'golden nugget' comments.

    Analyze all the provided information and create a comprehensive report that covers:
    1.  **Key Themes:** What are the main subjects being discussed?
    2.  **User Sentiments:** What are the prevailing opinions, feelings, and attitudes (e.g., excitement, concern, confusion)?
    3.  **Common Questions & Problems:** What are people frequently asking about or struggling with?
    4.  **Actionable Insights:** What are the most interesting, surprising, or useful pieces of information found?

    Structure your output as a clean, well-organized markdown document. Do not just list the data; synthesize it into a narrative.

    <raw_reddit_data>
    {llm_context_text}
    </raw_reddit_data>

    Generate the final, synthesized report.
    """
    
    print(f"\n-> Sending {len(llm_context_text)} characters of consolidated data to LLM for final report...")
    response = llm.invoke(prompt)
    final_report = response.content
    
    print(f"✅ Final report generated. Size: {len(final_report)} characters.")
    return final_report


def save_report_to_file(report: str, topic: str) -> str:
    """Saves the report to a markdown file and returns the file path."""
    filename = f"reddit_report_{topic.replace(' ', '_').lower()}_{int(time.time())}.md"
    print(f"\n💾 Saving report to file: {filename}")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✅ Report successfully saved to {filename}")
        print(f"📁 File size: {os.path.getsize(filename):,} bytes")
        return filename
    except Exception as e:
        print(f"❌ Failed to save report: {e}")
        return ""

def main():
    print("--- 🚀 Starting Social Media Agent ---")
    print("What do you want to do?")
    print("1. 📚 Reddit research and answer a question")
    print("2. 🌐 Generate and post content from a URL")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        topic = input("\n🔎 Enter the topic you want to research: ").strip()
        prompt = input("❓ Enter the question you want to ask based on the research: ").strip()

        print(f"\n📚 Researching topic: '{topic}' with prompt: '{prompt}'")
        try:
            # This part is mostly the same
            reddit = praw.Reddit(
                client_id=os.getenv('REDDIT_CLIENT_ID'),
                client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                user_agent='FaiqQazi Reddit Bot',
                username=os.getenv('REDDIT_USER_NAME'),
                password=os.getenv('REDDIT_PASSWORD')
            )
            print("✅ Reddit client initialized.")

            # --- NEW WORKFLOW STARTS HERE ---

            # 1. Find potential subreddits (using the improved function)
            subreddits = find_relevant_subreddits(topic, limit=5)
            if not subreddits:
                print("❌ No relevant subreddits found.")
                return

            # 2. Search within subreddits and filter for the best posts
            top_submissions, top_posts, top_comments = search_and_filter_posts(reddit, subreddits, topic)
            if not top_submissions and not top_posts and not top_comments:
                print("❌ Found subreddits, but no specific posts matched the topic. Exiting.")
                return
            
            # 3. Scrape ONLY the best posts
            consolidated_data = scrape_validated_posts(top_submissions, top_posts, top_comments)

            # --- END OF NEW WORKFLOW ---

            # The rest of the logic remains the same
            report = generate_report_from_posts(topic, consolidated_data)
            print("\n📜 Generated Report:\n")
            # For brevity, let's print the first 1000 chars of the report
            print(report[:1000] + "..." if len(report) > 1000 else report)

            report_file = save_report_to_file(report, topic)
            if report_file:
                print(f"📂 Report saved to: {report_file}")

            llm = ChatOpenAI(model="gpt-4", temperature=0.2, openai_api_key=os.getenv("OPENAI_API_KEY"))
            answer_prompt = f"""As an analytical expert, examine the following Reddit research report and answer the user's question: \"{prompt}\"

                First, analyze if and how the information in the report relates to the question:
                1. Identify any directly relevant facts, statistics, or insights
                2. Note any indirectly related themes or patterns
                3. Consider community sentiments and expert opinions mentioned

                Report Content:
                {report}

                Guidelines for your response:
                - Only use information from the report that is genuinely relevant to the question
                - If the report doesn't contain directly relevant information, you may provide a general answer but clearly indicate which parts are based on the report and which are not
                - Incorporate specific facts, numbers, or viewpoints from the report when applicable
                - If the report's content is too tangential to the question, acknowledge this and explain why
                
                Provide a well-reasoned answer that:
                - Starts with how the report's content relates to the question
                - Clearly distinguishes between report-based insights and general knowledge
                - Focuses on quality over comprehensiveness
                - Remains factual and objective

                main point is that relevance is key and you have to extract the facts and things from the report thhat are relevant to the users prompt and then give the answer based on those things dotn just go about and put the whole thing here targeted but relevant

                Structure your response as:
                RELEVANCE: [Briefly explain how the report content relates to the question]
                ANSWER: [Your response try to keep it as relevant to the user prompt as possible relevance is most important it may not be detailed but should be relevant]
                """
            response = llm.invoke(answer_prompt)
            print("\n💡 Answer to your question:")
            print(response.content)

        except Exception as e:
            print(f"❌ Error in Reddit research workflow: {e}")

    elif choice == "2":
        url = input("\n🌐 Enter the URL to scrape and summarize: ").strip()

        current_state: AgentState = {
            "url": url,
            "generated_text": "",
            "scraped_content": None
        }

        print(f"\n🌍 Processing URL: {current_state['url']}")

        try:
            formatted_content, raw_response = scrape_and_format_content(current_state["url"])
            current_state["scraped_content"] = formatted_content

            reddit_title, generated_text = generate_post_function(formatted_content)
            current_state["generated_text"] = generated_text

            all_image_urls = extract_images_from_firecrawl(raw_response)
            best_image_url = get_best_image_from_candidates(all_image_urls, generated_text)

            image_path = None
            if best_image_url:
                print(f"✅ Best image selected: {best_image_url}")
                image_path = "best_image_to_post.jpg"
                img_data = requests.get(best_image_url).content
                with open(image_path, "wb") as handler:
                    handler.write(img_data)
            else:
                print("⚠️ No suitable image selected.")

            # Use the generated title instead of hardcoded one
            reddit_url = post_to_reddit(reddit_title, generated_text, image_path=image_path)
            print("✅ Reddit post successful!")
            print(f"🔗 Reddit URL: {reddit_url}")
            print("✅ Reddit post successful!")
            print(f"🔗 Reddit URL: {reddit_url}")

            try:
                tweet_response = post_to_twitter_oauth1(generated_text)
                print("✅ Twitter post successful!")
                print(f"🐦 Tweet ID: {tweet_response.get('id')}")
            except Exception as e:
                print(f"❌ Twitter posting failed: {e}")

            if image_path and os.path.exists(image_path):
                os.remove(image_path)

        except Exception as e:
            print(f"❌ Error in social media posting workflow: {e}")

    else:
        print("❌ Invalid choice. Please enter 1 or 2.")

if __name__ == "__main__":
    main()