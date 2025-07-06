
import os
import requests
from typing import TypedDict, Optional, List, Dict
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
import streamlit as st

from src.services.firecrawl_client import scrape_and_format_content, extract_images_from_firecrawl
from src.services.gemini_client import get_best_image_from_candidates
from src.services.openai_client import generate_post_function, find_relevant_subreddits
from src.services.reddit_client import (
    post_to_reddit,
    search_and_filter_posts,
    validate_subreddit,
    scrape_validated_posts
)
from src.services.twitter_client import post_to_twitter_oauth1

# Core (Main Business Logic)
from src.core.report_generator import generate_report_from_posts
from src.core.agent import (
    route_user_request,
    execute_reddit_research_workflow,
    execute_url_posting_workflow,
    execute_direct_posting_workflow,
    execute_revision_workflow
)

from src.database import (
    create_user,
    verify_user,
    get_latest_report,
    save_chat_message,
    get_chat_history,
    save_research_report
)

from src.utils.file_handler import( save_report_to_file, save_raw_data_to_file)

from src.config import (
    OPENAI_API_KEY, FIRE_CRAWL_API_KEY, GEMINI_API_KEY,
    TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_SUBREDDIT,
    SUPABASE_URL, SUPABASE_KEY
)



def main():
    reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT', 'Social Media Agent by Faiq'),
    username=os.getenv('REDDIT_USERNAME'),
    password=os.getenv('REDDIT_PASSWORD')
)
    print("--- [MAIN] Starting Social Media Agent application ---")
    st.set_page_config(page_title="Social Media Agent", layout="wide")
    print("--- [MAIN] Streamlit page config set: title='Social Media Agent', layout='wide' ---")
    st.title("🚀 Social Media Content Agent")
    print("--- [MAIN] Displaying app title ---")

    # --- Step 1: Initialize Session State ---
    if 'logged_in' not in st.session_state:
        print("--- [SESSION] Initializing session state ---")
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.messages = []
        st.session_state.reddit_url_posted = None  # Initialize post URL state
        print(f"--- [SESSION] Session state initialized: logged_in={st.session_state.logged_in}, user_id={st.session_state.user_id}, username={st.session_state.username}, messages={len(st.session_state.messages)} ---")

    # --- Step 2: Show Login/Signup UI if not logged in ---
    if not st.session_state.logged_in:
        print("--- [AUTH] User not logged in, showing login/signup UI ---")
        st.header("Welcome!")
        print("--- [AUTH] Displaying 'Welcome!' header ---")
        
        # Create tabs for Login and Sign Up
        login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
        print("--- [AUTH] Created login and signup tabs ---")

        with login_tab:
            print("--- [AUTH] Rendering login tab ---")
            st.subheader("Login to your account")
            print("--- [AUTH] Displaying 'Login to your account' subheader ---")
            with st.form("login_form"):
                print("--- [AUTH] Rendering login form ---")
                login_username = st.text_input("Username", key="login_user")
                login_password = st.text_input("Password", type="password", key="login_pass")
                login_button = st.form_submit_button("Login")
                print(f"--- [AUTH] Login form inputs: username='{login_username}', password={'*' * len(login_password) if login_password else 'empty'} ---")

                if login_button:
                    print("--- [AUTH] Login button clicked ---")
                    if login_username and login_password:
                        print(f"--- [AUTH] Validating credentials for username: {login_username} ---")
                        with st.spinner("Verifying credentials..."):
                            print("--- [AUTH] Calling verify_user() ---")
                            user_data = verify_user(login_username, login_password)
                            print(f"--- [AUTH] verify_user() returned: {user_data} ---")
                            if user_data:
                                st.session_state.logged_in = True
                                st.session_state.user_id = user_data['id']
                                st.session_state.username = login_username
                                print(f"--- [AUTH] Login successful: user_id={user_data['id']}, username={login_username} ---")
                                print(f"--- [AUTH] Loading chat history for user_id: {user_data['id']} ---")
                                st.session_state.messages = get_chat_history(user_data['id'])
                                print(f"--- [AUTH] Chat history loaded: {len(st.session_state.messages)} messages ---")
                                st.success("Logged in successfully!")
                                print("--- [AUTH] Displaying success message: 'Logged in successfully!' ---")
                                time.sleep(1)
                                print("--- [AUTH] Rerunning app after successful login ---")
                                st.rerun()
                            else:
                                st.error("Invalid username or password.")
                                print("--- [AUTH] Login failed: Invalid username or password ---")
                    else:
                        st.warning("Please enter both username and password.")
                        print("--- [AUTH] Login failed: Missing username or password ---")

        with signup_tab:
            print("--- [AUTH] Rendering signup tab ---")
            st.subheader("Create a new account")
            print("--- [AUTH] Displaying 'Create a new account' subheader ---")
            with st.form("signup_form"):
                print("--- [AUTH] Rendering signup form ---")
                signup_username = st.text_input("Choose a Username", key="signup_user")
                signup_password = st.text_input("Choose a Password", type="password", key="signup_pass")
                signup_button = st.form_submit_button("Sign Up")
                print(f"--- [AUTH] Signup form inputs: username='{signup_username}', password={'*' * len(signup_password) if signup_password else 'empty'} ---")

                if signup_button:
                    print("--- [AUTH] Signup button clicked ---")
                    if signup_username and signup_password:
                        try:
                            print(f"--- [AUTH] Creating new user account for username: {signup_username} ---")
                            with st.spinner("Creating your account..."):
                                print("--- [AUTH] Calling create_user() ---")
                                new_user = create_user(signup_username, signup_password)
                                print(f"--- [AUTH] create_user() returned: {new_user} ---")
                                st.session_state.logged_in = True
                                st.session_state.user_id = new_user['id']
                                st.session_state.username = signup_username
                                st.session_state.messages = []
                                print(f"--- [AUTH] Signup successful: user_id={new_user['id']}, username={signup_username}, messages={len(st.session_state.messages)} ---")
                                st.success("Account created successfully! You are now logged in.")
                                print("--- [AUTH] Displaying success message: 'Account created successfully!' ---")
                                time.sleep(1)
                                print("--- [AUTH] Rerunning app after successful signup ---")
                                st.rerun()
                        except ValueError as e:
                            st.error(e)
                            print(f"--- [AUTH] Signup failed: {e} ---")
                        except Exception as e:
                            st.error(f"An error occurred: {e}")
                            print(f"--- [AUTH] Signup failed with unexpected error: {e} ---")
                    else:
                        st.warning("Please enter both a username and password.")
                        print("--- [AUTH] Signup failed: Missing username or password ---")
    
    # --- Step 3: Show the Main Chat Application if logged in ---
    else:
        print(f"--- [APP] User is logged in: username={st.session_state.username}, user_id={st.session_state.user_id} ---")
        st.sidebar.header(f"Welcome, {st.session_state.username}!")
        print(f"--- [APP] Displaying sidebar header: 'Welcome, {st.session_state.username}!' ---")
        if st.sidebar.button("Logout"):
            print("--- [APP] Logout button clicked ---")
            for key in list(st.session_state.keys()):
                print(f"--- [APP] Clearing session state key: {key} ---")
                del st.session_state[key]
            print("--- [APP] Session state cleared, rerunning app ---")
            st.rerun()

        st.write("Your AI assistant for Reddit research and content posting.")
        print("--- [APP] Displaying app description ---")

        # Display chat history
        print(f"--- [APP] Displaying chat history: {len(st.session_state.messages)} messages ---")
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                print(f"--- [APP] Displaying message: role={message['role']}, content='{message['content'][:50]}...' ---")

        # --- Post to Reddit Button ---
        st.markdown("---")
        st.subheader("📤 Ready to Post?")
        if st.session_state.get("reddit_url_posted"):
            st.success(f"✅ Successfully posted to Reddit: {st.session_state.reddit_url_posted}")
            st.markdown(f"[🔗 View Post on Reddit]({st.session_state.reddit_url_posted})")
        else:
            if st.button("🚀 Post Latest to Reddit"):
                print("=== [UI] Post to Reddit button clicked ===")
                messages = st.session_state.get("messages", [])
                latest_post = None

                # Find the latest assistant message
                for msg in reversed(messages):
                    if msg["role"] == "assistant":
                        latest_post = msg["content"]
                        break

                if not latest_post:
                    st.warning("⚠️ No assistant-generated content found to publish.")
                    print("❌ Could not find a suitable assistant message to post.")
                else:
                    # Parse title (if present, else generate default)
                    title_match = re.search(r"\*\*Title:\*\*\s*(.*)", latest_post)
                    reddit_title = title_match.group(1).strip() if title_match else f"Post by {st.session_state.username}"

                    # Parse text (use full content if no **Post Text:**)
                    text_match = re.search(r"\*\*Post Text:\*\*\n(.+?)(\n\n|\Z)", latest_post, re.DOTALL)
                    generated_text = text_match.group(1).strip() if text_match else latest_post.strip()

                    # Parse image (if any)
                    image_url = None
                    image_path = None
                    image_match = re.search(r"\*\*Suggested Image:\*\*\n(.+)", latest_post)
                    if image_match:
                        image_url = image_match.group(1).strip()
                        try:
                            img_data = requests.get(image_url).content
                            image_path = "temp_image_for_post.jpg"
                            with open(image_path, "wb") as handler:
                                handler.write(img_data)
                            print(f"🖼️ Downloaded image to: {image_path}")
                        except Exception as e:
                            print(f"❌ Failed to download image: {e}")
                            image_path = None

                    print(f"📤 Posting to Reddit with:\nTitle: {reddit_title}\nText: {generated_text[:200]}...\nImage: {image_path or 'None'}")

                    try:
                        with st.spinner("Posting to Reddit..."):
                            # Initialize Reddit client

                            reddit_url = post_to_reddit(reddit_title, generated_text, image_path=image_path)
                            st.session_state.reddit_url_posted = reddit_url
                            st.success(f"✅ Successfully posted to Reddit: {reddit_url}")
                            st.markdown(f"[🔗 View Post on Reddit]({reddit_url})")
                            print(f"✅ Posted to Reddit: {reddit_url}")
                            # Clean up temporary image file
                            if image_path and os.path.exists(image_path):
                                os.remove(image_path)
                                print(f"--- [CLEANUP] Deleted temporary image file: {image_path}")
                    except Exception as e:
                        st.error(f"❌ Failed to post to Reddit: {e}")
                        print(f"❌ Exception while posting to Reddit: {e}")

        # --- Get New User Input ---
        if user_prompt := st.chat_input("What would you like to do?"):
            print(f"--- [APP] User submitted prompt: '{user_prompt}' ---")
            save_chat_message(user_id=st.session_state.user_id, role="user", content=user_prompt)
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            print(f"--- [APP] Appended user message to session state: {len(st.session_state.messages)} messages total ---")
            with st.chat_message("user"):
                st.markdown(user_prompt)
                print("--- [APP] Displaying user prompt in chat UI ---")

            # Process the request with the assistant
            with st.chat_message("assistant"):
                with st.spinner("🧠 Analyzing your request..."):
                    print("--- [APP] Calling route_user_request() ---")
                    decision = route_user_request(user_prompt, st.session_state.messages)
                    print(f"--- [APP] route_user_request() returned: {decision} ---")
                    tool_to_call = decision.get("tool")
                    args = decision.get("args", {})
                    print(f"--- [APP] Selected tool: {tool_to_call}, args: {args} ---")

                response_content = ""
                if tool_to_call == "reddit_research":
                    topic = args.get("topic")
                    question = args.get("question")
                    print(f"--- [APP] Reddit research workflow selected: topic='{topic}', question='{question}' ---")
                    if topic and question:
                        print(f"--- [APP] Calling execute_reddit_research_workflow(user_id={st.session_state.user_id}, topic={topic}, question={question}) ---")
                        response_content = execute_reddit_research_workflow(st.session_state.user_id, topic, question)
                        print(f"--- [APP] Reddit research workflow returned: {response_content[:50]}... ---")
                    else:
                        response_content = "I need both a topic and a question for Reddit research."
                        print("--- [APP] Reddit research workflow failed: Missing topic or question ---")

                elif tool_to_call == "url_poster":
                    url = args.get("url")
                    print(f"--- [APP] URL posting workflow selected: url='{url}' ---")
                    if url:
                        print(f"--- [APP] Calling execute_url_posting_workflow(user_id={st.session_state.user_id}, url={url}) ---")
                        response_content = execute_url_posting_workflow(st.session_state.user_id, url)
                        print(f"--- [APP] URL posting workflow returned: {response_content[:50]}... ---")
                    else:
                        response_content = "I need a URL to post about."
                        print("--- [APP] URL posting workflow failed: Missing URL ---")
                elif tool_to_call == "revise_post":
                    revision_request = args.get("revision_request")
                    print(f"--- [APP] Revise post workflow selected: revision_request='{revision_request}' ---")
                    if revision_request:
                        print(f"--- [APP] Calling execute_revision_workflow(user_id={st.session_state.user_id}, revision_request={revision_request}) ---")
                        response_content = execute_revision_workflow(st.session_state.user_id, revision_request)
                        print(f"--- [APP] Revise workflow returned: {response_content[:50]}... ---")
                    else:
                        response_content = "I need specific revision instructions to proceed."
                        print("--- [APP] Revise workflow failed: Missing revision_request ---")
                elif tool_to_call == "direct_post":
                    text_to_post = args.get("text_to_post")
                    print(f"--- [APP] Direct post workflow selected: text_to_post='{text_to_post[:50] if text_to_post else ''}...' ---")
                    if text_to_post:
                        print(f"--- [APP] Calling execute_direct_posting_workflow(user_id={st.session_state.user_id}, text_to_post=<hidden>) ---")
                        response_content = execute_direct_posting_workflow(st.session_state.user_id, text_to_post)
                        print(f"--- [APP] Direct post workflow returned: {response_content[:50]}... ---")
                    else:
                        response_content = "Please provide the full text you'd like to post."
                        print("--- [APP] Direct post workflow failed: Missing text_to_post ---")
                else:
                    response_content = args.get("reason", "I'm sorry, I couldn't understand that request.")
                    print(f"--- [APP] Router error: {response_content} ---")

                # Display the final response and save to history
                st.markdown(response_content)
                print(f"--- [APP] Displaying assistant response: {response_content[:50]}... ---")
                st.session_state.messages.append({"role": "assistant", "content": response_content})
                print(f"--- [APP] Appended assistant response to session state: {len(st.session_state.messages)} messages total ---")

if __name__ == "__main__":
    print("--- [START] Executing main() ---")
    main()
    print("--- [END] main() execution completed ---")