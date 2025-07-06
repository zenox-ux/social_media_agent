# FILE: src/config.py

import os
from dotenv import load_dotenv

# Load environment variables from the .env file in the root directory
load_dotenv()

print("--- [CONFIG] Loading environment variables...")

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FIRE_CRAWL_API_KEY = os.getenv("FIRE_CRAWL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Twitter Credentials ---
TWITTER_CONSUMER_KEY = os.getenv("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.getenv("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

# --- Reddit Credentials ---
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'Social Media Agent by Faiq')
REDDIT_USERNAME = os.getenv('REDDIT_USERNAME')
REDDIT_PASSWORD = os.getenv('REDDIT_PASSWORD')
REDDIT_SUBREDDIT = os.getenv("REDDIT_SUBREDDIT", "test")

# --- Supabase Credentials ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


# --- Validation (Good Practice) ---
def validate_keys():
    if not all([OPENAI_API_KEY, FIRE_CRAWL_API_KEY, GEMINI_API_KEY]):
        raise ValueError("One or more essential API keys (OpenAI, FireCrawl, Gemini) are missing in .env")
    if not all([TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        print("⚠️ WARNING: Twitter credentials not found. Twitter features will be disabled.")
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        print("⚠️ WARNING: Reddit credentials not found. Reddit features will be disabled.")
    if not all([SUPABASE_URL, SUPABASE_KEY]):
        print("⚠️ WARNING: Supabase credentials not found. Database features will be disabled.")

print("--- [CONFIG] Environment variables loaded.")
validate_keys()