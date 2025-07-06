
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