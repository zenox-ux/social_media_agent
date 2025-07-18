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
print(reddit.user.me())