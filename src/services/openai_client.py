
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
    Prioritize niche subreddits over massive general ones. For example, for "Canadian immigration for tech workers", prefer r/ImmigrationCanada over just r/canada.try to find as many subreddits specifc to the topic
    give as many subreddits as possible, and try to exceed the limit if you can find more relevant ones.but relevance should be useful like if i search for ai agents it should not go search robotics and all instead it should look for specifc communities related to the topic for example langchain autocgpt are relevat communities                                                
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

  