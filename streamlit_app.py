

# --- Imports ---
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
from app import (
    find_relevant_subreddits,
    search_and_filter_posts,
    scrape_validated_posts,
    generate_report_from_posts,
    scrape_and_format_content,
    generate_post_function,
    extract_images_from_firecrawl,
    get_best_image_from_candidates,
    post_to_reddit,
    scrape_and_format_content,
    extract_images_from_firecrawl,
    get_best_image_from_candidates,
    save_report_to_file
)


# --- Load environment variables ---
print("--- [CONFIG] Loading environment variables...")
load_dotenv()

# --- API Key Checks ---
# (Your existing key checks are perfect and remain here)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# ... etc.
print("--- [CONFIG] Environment variables loaded.")

# --- Type Definitions ---
class AgentState(TypedDict):
    generated_text: str
    url: Optional[str]
    scraped_content: Optional[str]

# ==============================================================================
# --- CORE WORKFLOW FUNCTIONS ---
# ==============================================================================

def execute_reddit_research_workflow(topic: str, question: str) -> str:
    """Handles the entire Reddit research process and returns the final answer."""
    print("\n" + "="*50)
    print("--- 🚀 WORKFLOW START: Reddit Research ---")
    st.info(f"📚 Starting research on Reddit for topic: '{topic}'...")

    try:
        # Initialize Reddit client
        reddit = praw.Reddit(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            user_agent=os.getenv('REDDIT_USER_AGENT', 'Social Media Agent by Faiq'),
            username=os.getenv('REDDIT_USERNAME'),
            password=os.getenv('REDDIT_PASSWORD')
        )
        st.success("✅ Reddit client initialized.")

        # Find relevant subreddits
        with st.spinner("Finding relevant subreddits..."):
            subreddits = find_relevant_subreddits(topic, limit=5)
        if not subreddits:
            return "❌ Could not find any relevant subreddits for this topic."
        st.write(f"Found potential subreddits: `{', '.join(subreddits)}`")

        # Search and filter for the best posts
        with st.spinner("Searching for top posts and comments..."):
            top_submissions, top_posts, top_comments = search_and_filter_posts(reddit, subreddits, topic)
        if not any([top_submissions, top_posts, top_comments]):
            return "❌ No relevant posts or comments found matching the topic."
        st.write(f"Found {len(top_submissions)} top submissions, {len(top_posts)} top posts, and {len(top_comments)} top comments.")

        # Scrape the validated content
        with st.spinner("Scraping detailed content..."):
            consolidated_data = scrape_validated_posts(top_submissions, top_posts, top_comments)

        # Generate the comprehensive report
        with st.spinner("Synthesizing data into a research report... (This may take a moment)"):
            report = generate_report_from_posts(topic, consolidated_data)
            report_file = save_report_to_file(report, topic)
        st.success("✅ Research report generated.")

        
        # Answer the user's question based on the report
        with st.spinner("Formulating final answer..."):
            llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.2, openai_api_key=OPENAI_API_KEY)
            answer_prompt = f"""You are an expert analyst. Based *only* on the detailed research report provided below, answer the user's question.
            Synthesize the information from the report to provide a direct and concise answer. Do not add information not present in the report.

            <Research_Report>
            {report}
            </Research_Report>

            User's Question: "{question}"
            """
            response = llm.invoke(answer_prompt)
            final_answer = response.content
        
        st.info("Displaying report and answer below...")
        with st.expander("Click to view the full research report"):
            st.markdown(report)
            
        return final_answer
    except Exception as e:
        st.error(f"An error occurred during the Reddit research workflow: {e}")
        return f"❌ Workflow failed: {e}"


def execute_url_posting_workflow(url: str) -> str:
    """Handles the entire workflow for scraping a URL and posting content."""
    print("\n" + "="*50)
    print("--- 🚀 WORKFLOW START: URL Content Posting ---")
    st.info(f"🌍 Starting content generation from URL: {url}...")
    
    try:
        with st.spinner("Scraping and summarizing content..."):
            formatted_content, raw_response = scrape_and_format_content(url)
        st.success("✅ Content scraped and summarized.")

        with st.spinner("Generating post title and text..."):
            reddit_title, generated_text = generate_post_function(formatted_content)
        st.success("✅ Social media post generated.")

        with st.spinner("Finding and selecting the best image..."):
            all_image_urls = extract_images_from_firecrawl(raw_response)
            best_image_url = get_best_image_from_candidates(all_image_urls, generated_text)
        
        image_path = None
        if best_image_url:
            st.write(f"🖼️ Best image selected:")
            st.image(best_image_url)
            image_path = "temp_image_for_post.jpg"
            img_data = requests.get(best_image_url).content
            with open(image_path, "wb") as handler:
                handler.write(img_data)
        else:
            st.warning("⚠️ No suitable image was found or selected.")

        # Post to platforms
        results = []
        try:
            with st.spinner("Posting to Reddit..."):
                reddit_url = post_to_reddit(reddit_title, generated_text, image_path=image_path)
            results.append(f"✅ Successfully posted to Reddit: {reddit_url}")
        except Exception as e:
            results.append(f"❌ Failed to post to Reddit: {e}")

        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            
        return "\n\n".join(results)
    except Exception as e:
        st.error(f"An error occurred in the URL posting workflow: {e}")
        return f"❌ Workflow failed: {e}"


# ==============================================================================
# --- ROUTER FUNCTION (The Brains of the Operation) ---
# ==============================================================================

def route_user_request(user_prompt: str) -> dict:
    """
    Analyzes the user's prompt to decide which tool to use and extracts arguments.
    """
    print(f"\n--- [ROUTER] Analyzing user prompt: '{user_prompt}' ---")
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    router_prompt = f"""You are an intelligent routing agent. Your job is to analyze a user's prompt and determine which of two available tools to call. You must also extract the necessary arguments for that tool.

    The available tools are:
    1.  `reddit_research`: Use this tool if the user is asking a question or wants to find information about a general topic, sentiment, or what people are saying. It requires a 'topic' and a 'question'.
    2.  `url_poster`: Use this tool if the user provides a specific URL and wants to create and post content based on it. It requires a 'url'.

    Analyze the user's prompt below. Respond with ONLY a single, raw JSON object in the specified format. Do NOT add explanations or markdown formatting.

    Example for Reddit research:
    {{
      "tool": "reddit_research",
      "args": {{
        "topic": "software engineer job market canada",
        "question": "what are software engineers in canada saying about the job market"
      }}
    }}

    User Prompt: "{user_prompt}"
    """
    
    response = llm.invoke(router_prompt)
    raw_response_content = response.content.strip()
    print(f"--- [ROUTER] Raw LLM response:\n{raw_response_content}\n---")
    
    try:
        # Robustly find and parse the JSON object
        json_match = re.search(r'\{.*\}', raw_response_content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in the LLM response.")
        
        json_string = json_match.group(0)
        decision = json.loads(json_string)
        
        # --- THE CRITICAL FIX: NORMALIZE THE ARGUMENTS KEY ---
        # The LLM sometimes uses 'arguments' instead of 'args'. We handle both.
        if "arguments" in decision and "args" not in decision:
            print("--- [ROUTER] Normalizing 'arguments' key to 'args'...")
            decision["args"] = decision.pop("arguments")
        
        # --- Validation ---
        tool = decision.get("tool")
        args = decision.get("args", {})
        
        if not tool or not isinstance(args, dict):
            raise ValueError("Parsed JSON is malformed: missing 'tool' or 'args'.")
            
        if tool == "reddit_research" and not ("topic" in args and "question" in args):
             raise ValueError("Missing 'topic' or 'question' for reddit_research.")

        if tool == "url_poster" and not "url" in args:
             raise ValueError("Missing 'url' for url_poster.")

        print(f"--- [ROUTER] Decision successful: Call tool '{tool}' with args {args} ---")
        return decision

    except (json.JSONDecodeError, ValueError) as e:
        print(f"--- [ROUTER] ❌ Error parsing or validating router response: {e} ---")
        return {"tool": "error", "args": {"reason": f"Could not understand the request: {e}"}}
    except Exception as e:
        print(f"--- [ROUTER] ❌ Unexpected routing error: {e} ---")
        return {"tool": "error", "args": {"reason": f"An internal error occurred: {e}"}}

# ==============================================================================
# --- UTILITY AND WORKER FUNCTIONS ---
# (Place all your other functions like find_relevant_subreddits, generate_post_function, etc. here)
# ...
# ==============================================================================

# ==============================================================================
# --- STREAMLIT FRONTEND ---
# ==============================================================================

def main():
    st.set_page_config(page_title="Social Media Agent", layout="wide")
    st.title("🚀 Social Media Content Agent")
    st.write("Your AI assistant for Reddit research and content posting.")

    # Initialize session state for chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Display past messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Get user input
    if user_prompt := st.chat_input("What would you like to do?"):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Process the request
        with st.chat_message("assistant"):
            # 1. Route the request
            with st.spinner("🧠 Analyzing your request..."):
                decision = route_user_request(user_prompt)
                tool_to_call = decision.get("tool")
                args = decision.get("args", {})

            # 2. Execute the chosen workflow
            response_content = ""
            if tool_to_call == "reddit_research":
                topic = args.get("topic")
                question = args.get("question")
                if topic and question:
                    response_content = execute_reddit_research_workflow(topic=topic, question=question)
                else:
                    response_content = "I understood you want to research Reddit, but I had trouble identifying the specific topic and question. Could you please rephrase?"

            elif tool_to_call == "url_poster":
                url = args.get("url")
                if url:
                    response_content = execute_url_posting_workflow(url=url)
                else:
                    response_content = "I understood you want to post about a URL, but I couldn't find the link. Could you please provide it?"
            
            else: # Handles the 'error' case from the router
                response_content = args.get("reason", "I'm sorry, I couldn't understand that request. Please try again.")
            
            # 3. Display the final response and save to history
            st.markdown(response_content)
            st.session_state.messages.append({"role": "assistant", "content": response_content})

# It's better to move all function definitions outside of main() and then call main()
# This block should contain all your other functions that are currently in the script.
# For example:
# class AgentState(TypedDict): ...
# def post_to_twitter_oauth1(...): ...
# def find_relevant_subreddits(...): ...
# etc.

if __name__ == "__main__":
    # Create a placeholder `app.py` if needed for imports, or ensure all functions
    # are defined in this file before `main()` is called.
    # For a single file app, all function definitions should come before this block.
    main()