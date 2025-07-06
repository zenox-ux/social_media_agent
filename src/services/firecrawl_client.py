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
    

