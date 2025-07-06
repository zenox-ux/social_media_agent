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

