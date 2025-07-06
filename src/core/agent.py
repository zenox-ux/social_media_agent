
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




def execute_reddit_research_workflow(user_id: str, topic: str, question: str) -> str:

    """Handles the entire Reddit research process and returns the final answer."""
    print("\n" + "="*50)
    print("--- 🚀 WORKFLOW START: Reddit Research ---")
    st.info(f"📚 Starting research on Reddit for topic: '{topic}'...")
    report = None
    report_id = None
    
    with st.spinner("🧠 Checking for your most recent research report..."):
        found, latest_report = get_latest_report(user_id)
        found = bool(found)
        print(type(found))
    print(f"--- [CACHE CHECK] Found recent report: {found}, Topic: {latest_report['topic'] if found else 'N/A'}")

    if found:
        print(f"--- [CACHE CHECK] Found a recent report on topic: '{latest_report['topic']}'")
        with st.spinner("🤖 Asking AI if the existing report is relevant to your new question..."):
            # Configure Gemini
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in .env for relevance check.")
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash-latest')

            # Prompt to check relevance
            relevance_prompt = f"""You are a relevance analysis expert. Determine if an existing research report is sufficient to answer a new user question.

            **Existing Report Topic:** "{latest_report['topic']}"
            **Existing Report Summary (first 1000 chars):**
            ---
            {latest_report['content'][:1000]}...
            ---
            **New User Question:** "{question}"

            Can the new user question likely be answered using the existing report?
            Respond with ONLY a single, raw JSON object: {{"is_relevant": true/false, "reason": "Your brief reason here."}}
            """
            
            relevance_response = model.generate_content(relevance_prompt)
            
            try:
                # Robust JSON parsing
                json_match = re.search(r'\{.*\}', relevance_response.text, re.DOTALL)
                if not json_match: raise ValueError("No JSON in relevance response.")
                relevance_result = json.loads(json_match.group(0))
                is_relevant = relevance_result.get("is_relevant", False)
                reason = relevance_result.get("reason", "No reason provided.")
                print(f"--- [CACHE CHECK] Gemini decision: Relevant = {is_relevant}. Reason: {reason}")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"--- [CACHE CHECK] ⚠️ Could not parse relevance check response: {e}")
                is_relevant = False

        if is_relevant:
            print("--- [CACHE CHECK] ✅ Using existing report. Skipping new research.")
            st.success(f"💡 Found a relevant report on '{latest_report['topic']}'! Answering from cache.")
            report = latest_report['content']
            print("latest report")
            print(latest_report)
            report_id = latest_report['id']
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            answer_prompt = f"""You are a world-class research analyst and communication expert. Your task is to provide the best possible answer to a user's question, using ONLY the provided research report as your source of truth.

            **Your Thought Process (Follow these steps internally):**
            1.  **Analyze the User's Question:** First, understand the *intent* behind the question. Are they asking for:
                - A specific fact or data point?
                - A general summary of a topic?
                - A story, example, or personal experience (anecdote)?
                - The overall sentiment or opinions of the community?
            2.  **Scan the Report for Relevance:** Read through the entire research report and identify the 2-4 most relevant paragraphs, themes, or stories that directly address the user's question.
            3.  **Synthesize and Structure:** Based on the user's intent, synthesize the relevant information into a perfectly structured answer. Do NOT just copy-paste from the report.

            **Response Formatting Rules:**
            - If the user is asking for **facts or data**, provide a direct answer followed by bullet points with the supporting data.
            - If the user is asking for a **summary**, provide a concise paragraph followed by a clear, bulleted list of the key takeaways.
            - If the user is asking for a **story or anecdote**, retell the most relevant story from the report in a narrative format.
            - If the user is asking about **sentiment**, summarize the different viewpoints (e.g., "The community was largely positive, with some expressing concern about X...").
            - **Crucially:** If the report does not contain information to answer the question, you MUST explicitly state: "I'm sorry, but the research report does not contain specific information about that topic." Do not invent information.

            ---
            **<Research_Report>**
            {report}
            **</Research_Report>**
            ---

            **User's Question:** "{question}"

            ---
            **Your Final Answer:**
            """
            
            print("-> Sending advanced Q&A prompt to Gemini...")
            response = model.generate_content(answer_prompt)
            print("-> Gemini response received.")
            print(len(response.text), "characters in the response.")
            final_answer = response.text
            return final_answer

            
        else:
            print("--- [CACHE CHECK] ℹ️ Existing report is not relevant enough. Starting new research.")
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

            raw_report_file = save_raw_data_to_file(consolidated_data, topic)
            print(f"Raw report saved to: {raw_report_file}")
            # Generate the comprehensive report
            with st.spinner("Synthesizing data into a research report... (This may take a moment)"):
                report = generate_report_from_posts(topic, consolidated_data)
                report_file = save_report_to_file(report, topic)
            # NEW: Save the generated report to the database
            print("saving the report to the database...")
            report_id = save_research_report(user_id=user_id, topic=topic, content=report)
            print(f"Report saved with ID: {report_id}")
            st.success("✅ Research report generated and saved.")
            st.success("✅ Research report generated.")
                    # Answer the user's question based on the report
            with st.spinner("Formulating final answer..."):
                GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash-latest')

                # --- Step 2: The Advanced, Multi-Purpose Prompt ---
                answer_prompt = f"""You are a world-class research analyst and communication expert. Your task is to provide the best possible answer to a user's question, using ONLY the provided research report as your source of truth.

                **Your Thought Process (Follow these steps internally):**
                1.  **Analyze the User's Question:** First, understand the *intent* behind the question. Are they asking for:
                    - A specific fact or data point?
                    - A general summary of a topic?
                    - A story, example, or personal experience (anecdote)?
                    - The overall sentiment or opinions of the community?
                2.  **Scan the Report for Relevance:** Read through the entire research report and identify the 2-4 most relevant paragraphs, themes, or stories that directly address the user's question.
                3.  **Synthesize and Structure:** Based on the user's intent, synthesize the relevant information into a perfectly structured answer. Do NOT just copy-paste from the report.

                **Response Formatting Rules:**
                - If the user is asking for **facts or data**, provide a direct answer followed by bullet points with the supporting data.
                - If the user is asking for a **summary**, provide a concise paragraph followed by a clear, bulleted list of the key takeaways.
                - If the user is asking for a **story or anecdote**, retell the most relevant story from the report in a narrative format.
                - If the user is asking about **sentiment**, summarize the different viewpoints (e.g., "The community was largely positive, with some expressing concern about X...").
                - **Crucially:** If the report does not contain information to answer the question, you MUST explicitly state: "I'm sorry, but the research report does not contain specific information about that topic." Do not invent information.

                ---
                **<Research_Report>**
                {report}
                **</Research_Report>**
                ---

                **User's Question:** "{question}"

                ---
                **Your Final Answer:**
                """
                
                print("-> Sending advanced Q&A prompt to Gemini...")
                response = model.generate_content(answer_prompt)
                print("-> Gemini response received.")
                print(len(response.text), "characters in the response.")
                final_answer = response.text
                save_chat_message(user_id=user_id, role="assistant", content=final_answer, report_id=report_id)
                # THIS EXPANDER WILL NOW ALWAYS BE DISPLAYED
                with st.expander("Click to view the full research report used for this answer"):
                    st.markdown(report)
                if os.path.exists(raw_report_file) and raw_report_file :
                    with open(raw_report_file, "r", encoding="utf-8") as f:
                        report_content = f.read()

                    with st.expander("Click to view the full raw research report used for this answer"):
                        st.markdown(report_content)
                else:
                    st.warning("⚠️ Raw Report file not found or could not be read.")
            

                
            return final_answer
    else:
        print("--- [CACHE CHECK] ℹ️ there is no existing report making the first one.")
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
            raw_report_file = save_raw_data_to_file(consolidated_data, topic)
        # Generate the comprehensive report
        with st.spinner("Synthesizing data into a research report... (This may take a moment)"):
            report = generate_report_from_posts(topic, consolidated_data)
            report_file = save_report_to_file(report, topic)
        # NEW: Save the generated report to the database
        print("saving the report to the database...")
        report_id = save_research_report(user_id=user_id, topic=topic, content=report)
        print(f"Report saved with ID: {report_id}")
        st.success("✅ Research report generated and saved.")
        st.success("✅ Research report generated.")
                # Answer the user's question based on the report
        with st.spinner("Formulating final answer..."):
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash-latest')

            # --- Step 2: The Advanced, Multi-Purpose Prompt ---
            answer_prompt = f"""You are a world-class research analyst and communication expert. Your task is to provide the best possible answer to a user's question, using ONLY the provided research report as your source of truth.

            **Your Thought Process (Follow these steps internally):**
            1.  **Analyze the User's Question:** First, understand the *intent* behind the question. Are they asking for:
                - A specific fact or data point?
                - A general summary of a topic?
                - A story, example, or personal experience (anecdote)?
                - The overall sentiment or opinions of the community?
            2.  **Scan the Report for Relevance:** Read through the entire research report and identify the 2-4 most relevant paragraphs, themes, or stories that directly address the user's question.
            3.  **Synthesize and Structure:** Based on the user's intent, synthesize the relevant information into a perfectly structured answer. Do NOT just copy-paste from the report.

            **Response Formatting Rules:**
            - If the user is asking for **facts or data**, provide a direct answer followed by bullet points with the supporting data.
            - If the user is asking for a **summary**, provide a concise paragraph followed by a clear, bulleted list of the key takeaways.
            - If the user is asking for a **story or anecdote**, retell the most relevant story from the report in a narrative format.
            - If the user is asking about **sentiment**, summarize the different viewpoints (e.g., "The community was largely positive, with some expressing concern about X...").
            - **Crucially:** If the report does not contain information to answer the question, you MUST explicitly state: "I'm sorry, but the research report does not contain specific information about that topic." Do not invent information.

            ---
            **<Research_Report>**
            {report}
            **</Research_Report>**
            ---

            **User's Question:** "{question}"

            ---
            **Your Final Answer:**
            """
            
            print("-> Sending advanced Q&A prompt to Gemini...")
            response = model.generate_content(answer_prompt)
            print("-> Gemini response received.")
            print(len(response.text), "characters in the response.")
            final_answer = response.text
            save_chat_message(user_id=user_id, role="assistant", content=final_answer, report_id=report_id)
            st.info("Displaying the full report below (click to expand).")
            # THIS EXPANDER WILL NOW ALWAYS BE DISPLAYED
            with st.expander("Click to view the full research report used for this answer"):
                st.markdown(report)
            if os.path.exists(raw_report_file) and raw_report_file :
                with open(raw_report_file, "r", encoding="utf-8") as f:
                    report_content = f.read()

                with st.expander("Click to view the full raw research report used for this answer"):
                    st.markdown(report_content)
            else:
                st.warning("⚠️Raw Report file not found or could not be read.")
                    

        return final_answer
        



def execute_url_posting_workflow(user_id: str,url: str) -> str:
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
        content_to_save = f"**Title:** {reddit_title}\n\n**Post Text:**\n{generated_text}"

        save_chat_message(user_id=user_id, role="assistant", content=content_to_save, report_id=None)
        print("-> Saved generated post preview to chat history.")

        
        # 🔽 Display the generated content to the user
        st.subheader("📝 Generated Reddit Post")
        # st.markdown(f"**Title:** {reddit_title}")
        # st.markdown(f"**Post Text:**\n\n{generated_text}")

        with st.spinner("Finding and selecting the best image..."):
            all_image_urls = extract_images_from_firecrawl(raw_response)
            best_image_url = get_best_image_from_candidates(all_image_urls, generated_text)
        
        image_path = None
        if best_image_url:
            # st.write(f"🖼️ Best image selected:")
            # st.image(best_image_url)
            image_path = "temp_image_for_post.jpg"
            img_data = requests.get(best_image_url).content
            with open(image_path, "wb") as handler:
                handler.write(img_data)
        else:
            st.warning("⚠️ No suitable image was found or selected.")

        if best_image_url:
            content_to_save += f"\n\n**Suggested Image:**\n{best_image_url}"

        # if image_path and os.path.exists(image_path):
        #     os.remove(image_path)
            
        return content_to_save
    except Exception as e:
        st.error(f"An error occurred in the URL posting workflow: {e}")
        return f"❌ Workflow failed: {e}"


# ==============================================================================
# --- ROUTER FUNCTION (The Brains of the Operation) ---
# ==============================================================================

def route_user_request(user_prompt: str, chat_history: List[Dict[str, str]]) -> dict:
    """
    Analyzes the user's prompt and chat history to decide which tool to use.
    """
    print(f"\n--- [ROUTER] Analyzing user prompt with chat history...")

    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    formatted_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

    router_prompt = f"""You are an intelligent routing agent. Your job is to analyze the latest user prompt in the context of the entire chat history and determine which of the four available tools is appropriate to call.

    **Chat History:**
    <history>
    {formatted_history}
    </history>

    **Available Tools:**
    1. `revise_post`: Use this tool if the user wants to change or edit the most recent assistant message.  
        - Required field: `"revision_request"` (a single string describing all changes, such as: "Change the title to 'New Title' and add a line at the end that says 'Faiq has said all of this.'")

    2. `direct_post`: Use this tool if the user provides full text and explicitly wants to publish it.  
        - Required field: `"text_to_post"` (the full content to post)

    3. `reddit_research`: Use this tool if the user is asking about general Reddit-based questions, public sentiment, or real opinions.  
        - Required fields: `"topic"` and `"question"`

    4. `url_poster`: Use this if the user provides a URL and wants to auto-generate a social media post from it.  
        - Required field: `"url"`

    Respond ONLY with a valid raw JSON object using one of the tool formats below. Do NOT add any explanation or Markdown.

    **Reddit Research Example:**
    {{ "tool": "reddit_research", "args": {{ "topic": "ai jobs germany", "question": "what is the situation of ai job market in germany?" }} }}

    **URL Poster Example:**
    {{ "tool": "url_poster", "args": {{ "url": "https://example.com" }} }}

    **Revise Post Example:**
    {{ "tool": "revise_post", "args": {{ "revision_request": "Change the title to 'AI Trends 2025' and add 'This was written by Faiq.' at the end." }} }}

    **Direct Post Example:**
    {{ "tool": "direct_post", "args": {{ "text_to_post": "Here is the complete post text the user wants to share..." }} }}

    **User Prompt:** "{user_prompt}"
    """


    response = llm.invoke(router_prompt)
    raw_response_content = response.content.strip()
    print(f"--- [ROUTER] Raw LLM response:\n{raw_response_content}\n---")

    try:
        json_match = re.search(r'\{.*\}', raw_response_content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in LLM response.")

        json_string = json_match.group(0)
        decision = json.loads(json_string)

        # Normalize if "arguments" is used
        if "arguments" in decision and "args" not in decision:
            decision["args"] = decision.pop("arguments")

        # Handle flat cases like { "url": "..." }
        if "tool" not in decision:
            if "url" in decision:
                decision = {
                    "tool": "url_poster",
                    "args": {"url": decision["url"]}
                }
            elif "text_to_post" in decision:
                decision = {
                    "tool": "direct_post",
                    "args": {"text_to_post": decision["text_to_post"]}
                }
            else:
                raise ValueError("Malformed JSON: missing 'tool' or unrecognized structure.")

        tool = decision.get("tool")
        args = decision.get("args", {})

        if not tool or not isinstance(args, dict):
            raise ValueError("Malformed JSON: missing 'tool' or 'args'.")

        # Per-tool validation
        if tool == "reddit_research" and not ("topic" in args and "question" in args):
            raise ValueError("Missing 'topic' or 'question' for reddit_research.")
        if tool == "url_poster" and "url" not in args:
            raise ValueError("Missing 'url' for url_poster.")
        if tool == "revise_post" and "revision_request" not in args:
            raise ValueError("Missing 'revision_request' for revise_post.")
        if tool == "direct_post" and "text_to_post" not in args:
            raise ValueError("Missing 'text_to_post' for direct_post.")

        print(f"--- [ROUTER] ✅ Decision: tool = '{tool}', args = {args}")
        return decision

    except (json.JSONDecodeError, ValueError) as e:
        print(f"--- [ROUTER] ❌ Parsing/validation error: {e}")
        return {"tool": "error", "args": {"reason": f"Could not understand the request: {e}"}}
    except Exception as e:
        print(f"--- [ROUTER] ❌ Unexpected error: {e}")
        return {"tool": "error", "args": {"reason": f"An internal error occurred: {e}"}}


def execute_revision_workflow(user_id: str, revision_request: str) -> str:
    """
    Revises the most recent assistant-generated post based on user feedback.
    Extracts from st.session_state.messages instead of session_state.post_draft.
    """
    print("\n" + "="*50)
    print("--- 🚀 WORKFLOW START: Post Revision ---")
    st.info(f"✍️ Revising the draft with your feedback: '{revision_request}'...")
    print("the messages in the session state:")
    print(st.session_state.messages)
    # Ensure chat history exists
    messages = st.session_state.get("messages", [])
    print("the messages found by the current syntax are:")
    print(messages)
    print(f"🔍 Total messages in session: {len(messages)}")

    # Find the latest assistant message that contains the original post
    last_assistant_post = None
    for msg in reversed(messages):
        if msg["role"] == "assistant" and "**Post Text:**" in msg["content"]:
            last_assistant_post = msg["content"]
            break

    if not last_assistant_post:
        error_msg = "❌ Could not find a previously generated post to revise. Please create a post first."
        st.error(error_msg)
        return error_msg

    print("✅ Found previous assistant post for revision.")
    
    # Extract title and post text
    title = "Untitled"
    original_post_text = ""
    
    try:
        title_match = re.search(r"\*\*Title:\*\*\s*(.*)", last_assistant_post)
        if title_match:
            title = title_match.group(1).strip()
            print(f"📝 Extracted Title: {title}")

        text_match = re.search(r"\*\*Post Text:\*\*\n(.+?)(\n\n|\Z)", last_assistant_post, re.DOTALL)
        if text_match:
            original_post_text = text_match.group(1).strip()
            print(f"📝 Extracted Post Text:\n{original_post_text[:200]}...")  # Print first 200 chars
        else:
            raise ValueError("Post Text not found.")
    except Exception as e:
        error_msg = f"❌ Failed to extract original content: {e}"
        st.error(error_msg)
        return error_msg

    # LLM-based revision
    with st.spinner("Revising the post..."):
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7, openai_api_key=OPENAI_API_KEY)
        revision_prompt = f"""You are a copy editor. Revise the following social media post based on the user's instructions.

<Original_Post_Text>
{original_post_text}
</Original_Post_Text>

<User_Revision_Request>
{revision_request}
</User_Revision_Request>

Provide ONLY the full, revised post text as your response.
"""
        response = llm.invoke(revision_prompt)
        revised_post_text = response.content.strip()

    print(f"✏️ Revised Post Text:\n{revised_post_text}...")  # Preview first 200 chars

    # Optional: preserve any image link if present in previous response
    image_url = None
    image_match = re.search(r"\*\*Suggested Image:\*\*\n(.+)", last_assistant_post)
    if image_match:
        image_url = image_match.group(1).strip()
        print(f"🖼️ Preserved image URL: {image_url}")

    # Construct revised message preview
    revised_preview = ""
    revised_preview += f"**Title:** {title}\n\n"
    revised_preview += f"**Post Text:**\n{revised_post_text}\n\n"
    if image_url:
        revised_preview += f"**Suggested Image:**\n{image_url}"
    print("📦 Revised post preview constructed.")
    print(revised_preview)
    # Append to Streamlit message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.session_state.messages.append({
        "role": "assistant",
        "content": revised_preview
    })

    print("✅ Revised post added to Streamlit session state.")
    
    st.success("✅ Post draft revised successfully!")
    save_chat_message(user_id=user_id, role="assistant", content=revised_preview)
    return revised_preview



def execute_direct_posting_workflow(user_id: str, text_to_post: str) -> str:
    """
    Directly posts user-provided text to social media platforms.
    """
    print("\n" + "="*50)
    print("--- 🚀 WORKFLOW START: Direct Posting ---")
    st.info(f"📬 Preparing to post your content directly...")

    # Generate a generic title if needed
    title = f"A new post from {st.session_state.username}"
    print(f"📝 Using title: {title}")

    # Format assistant message
    formatted_post = f"**Title:** {title}\n\n**Post Text:**\n{text_to_post}"
    print("📦 Formatted post:\n", formatted_post[:200], "...")  # Preview

    # Display to user
    st.subheader("📝 Content to be Posted")
    st.markdown(formatted_post)

    # Save to Streamlit session messages
    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.session_state.messages.append({
        "role": "assistant",
        "content": formatted_post
    })
    print("✅ Assistant message added to session state.")

    # Save to DB (optional logging)
    save_chat_message(user_id=user_id, role="assistant", content=formatted_post)

    st.success("✅ Post content saved and ready!")

    return formatted_post


