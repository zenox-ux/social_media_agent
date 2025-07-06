
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





def save_raw_data_to_file(consolidated_data: list[dict], topic: str) -> str:
    """
    Saves the raw, consolidated data to a JSON file for debugging and review.

    Args:
        consolidated_data: The list of dictionaries from `scrape_validated_posts`.
        topic: The research topic to include in the filename.

    Returns:
        The path to the saved file.
    """
    # Create a unique filename to avoid overwriting
    filename = f"raw_data_{topic.replace(' ', '_').lower()}_{int(time.time())}.json"
    print(f"\n💾 Saving raw consolidated data to file: {filename}")
    
    try:
        # Use json.dump for pretty-printing the list of dictionaries
        with open(filename, 'w', encoding='utf-8') as f:
            # indent=2 makes the JSON file human-readable
            json.dump(consolidated_data, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Raw data successfully saved to {filename}")
        print(f"📁 File size: {os.path.getsize(filename):,} bytes")
        return filename
    except Exception as e:
        print(f"❌ Failed to save raw data file: {e}")
        return "" # Return an empty string on failure



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