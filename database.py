import os
import uuid
import bcrypt
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# --- Initialization ---
load_dotenv()
url: Optional[str] = os.environ.get("SUPABASE_URL")
key: Optional[str] = os.environ.get("SUPABASE_KEY")
print("Initializing Supabase client...")
print(url)
print(key)

if not url or not key:
    print("⚠️ WARNING: SUPABASE_URL or SUPABASE_KEY not found. Database features will be disabled.")
    supabase: Optional[Client] = None
else:
    supabase: Optional[Client] = create_client(url, key)
    print("✅ Supabase client initialized.")


# ==============================================================================
# --- USER AUTHENTICATION FUNCTIONS ---
# ==============================================================================
def create_user(username: str, password: str) -> None:
    """
    Creates a new user in the 'social_media_users' table with a securely hashed password.
    Does not return anything. Logs steps via print statements.
    """
    if not supabase:
        raise ConnectionError("❌ Supabase client not initialized. Please connect to the database.")

    print(f"🔐 Creating user: {username}")
    
    try:
        # Step 1: Hash the password
        print("🔑 Hashing password...")
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        print("✅ Password hashed.")

        # Step 2: Attempt to insert the new user
        print("📥 Inserting user into database...")
        response = supabase.table("social_media_users").insert({
            "username": username,
            "hashed_password": hashed_password
        }).execute()
        print(response  )
        new_user = response.data[0]
        print(f"✅ User created: {new_user}")
        return new_user
        

    except Exception as e:
        print(f"❌ Exception occurred during user creation: {e}")

def get_latest_report(user_id: str) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Retrieves the most recent research report for a given user.
    Returns a tuple: (found: bool, report: Optional[Dict])
    """
    if not supabase: 
        return False, None

    print(f"-> DB: Fetching the most recent report for user {user_id[-6:]}...")

    try:
        response = supabase.table('social_media_research_reports') \
            .select('id, topic, content, created_at') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()

        reports = response.data
        if reports and len(reports) > 0:
            report = reports[0]
            print(f"✅ DB: Found a recent report on topic '{report['topic']}'")
            return True, report
        else:
            print("-> DB: No previous reports found for this user.")
            return False, None

    except Exception as e:
        print(f"⚠️ DB: Unexpected error fetching latest report: {e}")
        return False, None

    
def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a user's password against the stored hash.
    Returns user data (including ID) if successful, otherwise None.
    """
    if not supabase:
        raise ConnectionError("Database not connected. Cannot verify user.")

    print(f"-> Verifying credentials for user: '{username}'")
    # Find the user in the database by their username
    response = supabase.table('social_media_users').select('id, hashed_password').eq('username', username).single().execute()
    
    if not response.data:
        print(f"-> Login failed: User '{username}' not found.")
        return None
    
    user_data = response.data
    stored_hash = user_data.get('hashed_password')
    
    # Securely compare the provided password with the stored hash
    if stored_hash and bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        print(f"✅ Login successful for user '{username}'.")
        return user_data
    else:
        print(f"-> Login failed: Incorrect password for user '{username}'.")
        return None

# ==============================================================================
# --- CHAT & REPORT MANAGEMENT FUNCTIONS ---
# ==============================================================================

def save_chat_message(user_id: str, role: str, content: str, report_id: Optional[str] = None):
    """Saves a single chat message to the 'social_media_chat_history' table."""
    if not supabase: return
    
    print(f"-> Saving chat message to DB for user {user_id[-6:]}. Role: {role}")
    message_data = {
        'user_id': user_id,
        'role': role,
        'content': content,
        'report_id': report_id
    }
    response = supabase.table('social_media_chat_history').insert(message_data).execute()
    print("-> Chat message saved to DB.")
    print(response)


def save_research_report(user_id: str, topic: str, content: str) -> str:
    """Saves a generated research report to 'social_media_research_reports' and returns its ID."""
    if not supabase: 
        # Return a random UUID if DB is disabled so the app doesn't crash
        return str(uuid.uuid4())

    print(f"-> Saving research report to DB on topic '{topic}' for user {user_id[-6:]}...")
    report_data = {
        'user_id': user_id,
        'topic': topic,
        'content': content
    }
    response = supabase.table('social_media_research_reports').insert(report_data).execute()
    
    if response.data:
        report_id = response.data[0]['id']
        print(f"✅ Report saved with ID: {report_id}")
        return report_id
    else:
        raise Exception(f"Failed to save report to database: {response.error}")

def get_chat_history(user_id: str) -> List[Dict[str, Any]]:
    """Retrieves chat history for a given user from 'social_media_chat_history'."""
    if not supabase: return []
    
    print(f"-> Fetching chat history from DB for user {user_id[-6:]}...")
    response = supabase.table('social_media_chat_history').select('role, content').eq('user_id', user_id).order('created_at', desc=False).execute()
    
    if response.data:
        print(f"✅ Found {len(response.data)} previous messages.")
        return response.data
    
    print("-> No previous chat history found for this user.")
    return []