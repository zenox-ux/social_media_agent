import praw
import os
# Initialize the Reddit API client
from dotenv import load_dotenv

load_dotenv() 
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent='FaiqQazi Reddit Bot',
    username=os.getenv('REDDIT_USER_NAME'),
    password=os.getenv('REDDIT_PASSWORD')
)

# Choose the subreddit and post title/body
subreddit = reddit.subreddit("test")  # change to your desired subreddit
title = "Hello from the Reddit API!"
body = "This post was made using the Reddit API and Python 🐍"

# Create the post
submission = subreddit.submit(title, selftext=body)

print(f"✅ Post successful! URL: {submission.url}")
