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


def generate_report_from_posts(topic: str, consolidated_data: list[dict]) -> str:
    """
    Generates a deep, narrative-rich report from consolidated Reddit data using a
    two-turn conversational approach with the Gemini API.
    """
    print("\n📝 Generating DEEP report from consolidated Reddit data using Gemini...")

    # --- Step 1: Configure Gemini ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY not found. Cannot generate Gemini report.")
        return "# Report Generation Failed\n\nGemini API Key is not configured."

    genai.configure(api_key=GEMINI_API_KEY)
    # Using gemini-1.5-flash for speed and its large context window.
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    # Start a chat session to maintain context between the two turns
    chat = model.start_chat()

    # --- Step 2: Format the data into a single text block ---
    # (This part is similar to before, but with better print statements)
    llm_context_text = ""
    print("-> Formatting consolidated data for the LLM prompts...")

    for i, item in enumerate(consolidated_data):
        item_type = item.get('type', 'unknown')
        if item_type == 'full_submission':
            llm_context_text += f"\n\n--- Discussion Thread Start ---\nTitle: {item.get('title', 'N/A')}\nPost Body: {item.get('selftext', 'No body text.')}\n"
            if item.get('top_comments'):
                llm_context_text += "Key Comments:\n"
                for c in item['top_comments']:
                    llm_context_text += f"- (Score: {c.get('score', 0)}) {c.get('body', '')}\n"
            llm_context_text += "--- Discussion Thread End ---\n"
        elif item_type == 'individual_post':
            llm_context_text += f"\n\n--- Relevant Post ---\nTitle: {item.get('title', 'N/A')}\nPost Body: {item.get('selftext', '')}\n--- End Relevant Post ---\n"
        elif item_type == 'comment_nuggets':
            llm_context_text += f"\n\n--- Highly Relevant Individual Comments ---\n"
            if item.get('comments'):
                for c in item['comments']:
                    llm_context_text += f"- (Score: {c.get('score', 0)}) \"{c.get('body', '')}\"\n"
            llm_context_text += "--- End Individual Comments ---\n"
    
    if not llm_context_text.strip():
        print("⚠️ No valid data was formatted. Aborting report generation.")
        return f"# Report on {topic}\n\nNo relevant content could be processed."

    # --- Step 3: Split the data for the two-turn conversation ---
    print(f"-> Total context size: {len(llm_context_text)} characters. Splitting into two turns.")
    midpoint = len(llm_context_text) // 2
    part1_text = llm_context_text[:midpoint]
    part2_text = llm_context_text[midpoint:]

    # --- Step 4: First Turn - Ingest and Initial Analysis ---
    prompt1 = f"""You are a world-class research analyst building a deep and comprehensive knowledge base about the topic: '{topic}'.
    I am providing you with the first half of the raw data scraped from Reddit. This data includes full discussion threads, individual relevant posts, and curated 'golden nugget' comments.

    Your task for this first step is to read, understand, and internally process all of this information. Identify preliminary key themes, interesting stories or anecdotes, and user sentiments.

    Acknowledge that you have received and processed this first part. Conclude your response with the phrase "Ready for Part 2." so I know you are prepared for the next set of data. Do not generate the full report yet.

    <raw_reddit_data_part_1>
    {part1_text}
    </raw_reddit_data_part_1>
    """
    
    try:
        print("\n-> Sending Part 1 of the data to Gemini...")
        response1 = chat.send_message(prompt1)
        print(f"✅ Gemini acknowledged Part 1. Response: \"{response1.text[:100]}...\"")

        # --- Step 5: Second Turn - Ingest, Synthesize, and Generate Full Report ---
        prompt2 = f"""Excellent. Now, here is the second and final part of the raw data.

        <raw_reddit_data_part_2>
        {part2_text}
        </raw_reddit_data_part_2>

        Now, using the information from BOTH Part 1 and Part 2, generate a single, final, comprehensive report. The report should be very detailed and well-structured to serve as a knowledge base for answering questions.

        Structure the report with the following detailed sections:
        1.  **Executive Summary:** A high-level overview of the entire discussion.
        2.  **Key Themes & Sub-Topics:** A deep dive into the 3-5 main themes that emerged. For each theme, explain it in detail.
        3.  **Prevailing Sentiments:** Analyze the overall mood. Is it positive, negative, mixed, concerned, excited? Use direct (but anonymous) sentiment examples.
        4.  **Common Questions & Unanswered Problems:** What are people consistently asking? What problems are they trying to solve?
        5.  **Notable Stories & Anecdotes:** Extract and retell 2-3 specific, compelling user stories or personal experiences that were shared. These are crucial for adding a human element. Quote short, impactful parts if necessary.
        6.  **Actionable Insights & Data Points:** List any specific advice, statistics, or hard facts that were mentioned.

        Your final output should be ONLY the complete markdown report. Be as detailed and comprehensive as possible.
        """
        
        print("\n-> Sending Part 2 and requesting the final report...")
        final_response = chat.send_message(prompt2)
        final_report = final_response.text
        
        print(f"✅ Final deep report generated. Size: {len(final_report)} characters.")
        return final_report

    except Exception as e:
        print(f"❌ An error occurred during Gemini report generation: {e}")
        return f"# Report Generation Failed\n\nAn error occurred while communicating with the Gemini API: {e}"
