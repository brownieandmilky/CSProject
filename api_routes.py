# api_routes.py

from flask import Blueprint, jsonify, session
from functools import wraps
import requests
import json
import random

# Import the shared database object from your central setup file
from firebase_setup import database


# --- Blueprint and Decorator Setup ---
api = Blueprint('api', __name__)

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'id_token' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function


# --- API Routes ---
@api.route('/entries', methods=['GET'])
@api_login_required
def get_user_entries():
    try:
        user_id = session['user_id']
        id_token = session['id_token']
        all_entries = database.child("entries").get(token=id_token)
        user_entries = []
        if all_entries.each():
            for entry in all_entries.each():
                data = entry.val()
                if data.get('uid') == user_id:
                    data['id'] = entry.key()
                    user_entries.append(data)
        user_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(user_entries)
    except Exception as e:
        return jsonify({"error": "Failed to fetch entries", "details": str(e)}), 500

@api.route('/quote', methods=['GET'])
@api_login_required
def get_daily_quote():
    """
    Fetches a random inspirational quote from multiple free APIs.
    Falls back to local quotes if all APIs fail.
    """
    
    # Fallback quotes in case all APIs fail
    fallback_quotes = [
        {"quote": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
        {"quote": "Life is what happens to you while you're busy making other plans.", "author": "John Lennon"},
        {"quote": "The future belongs to those who believe in the beauty of their dreams.", "author": "Eleanor Roosevelt"},
        {"quote": "It is during our darkest moments that we must focus to see the light.", "author": "Aristotle"},
        {"quote": "Success is not final, failure is not fatal: it is the courage to continue that counts.", "author": "Winston Churchill"},
        {"quote": "The only impossible journey is the one you never begin.", "author": "Tony Robbins"},
        {"quote": "In the middle of difficulty lies opportunity.", "author": "Albert Einstein"},
        {"quote": "Believe you can and you're halfway there.", "author": "Theodore Roosevelt"},
        {"quote": "The only thing we have to fear is fear itself.", "author": "Franklin D. Roosevelt"},
        {"quote": "Be yourself; everyone else is already taken.", "author": "Oscar Wilde"}
    ]
    
    # List of free quote APIs to try
    apis_to_try = [
        {
            "url": "https://api.quotable.io/random",
            "content_key": "content",
            "author_key": "author"
        },
        {
            "url": "https://zenquotes.io/api/random",
            "content_key": "q",
            "author_key": "a",
            "is_array": True
        },
        {
            "url": "https://api.adviceslip.com/advice",
            "content_key": "slip.advice",
            "author_key": None,
            "nested": True
        }
    ]
    
    # Try each API
    for api_config in apis_to_try:
        try:
            response = requests.get(api_config["url"], timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Handle array responses (like ZenQuotes)
            if api_config.get("is_array", False):
                data = data[0]
            
            # Handle nested responses (like AdviceSlip)
            if api_config.get("nested", False):
                content = data
                for key in api_config["content_key"].split('.'):
                    content = content[key]
            else:
                content = data.get(api_config["content_key"])
            
            # Get author (if available)
            if api_config["author_key"]:
                author = data.get(api_config["author_key"])
                # Clean up ZenQuotes author format
                if author and author.endswith(', '):
                    author = author[:-2]
            else:
                author = "Unknown"
            
            if content:
                return jsonify({
                    "quote": content,
                    "author": author
                })
                
        except Exception as e:
            print(f"API {api_config['url']} failed: {str(e)}")
            continue
    
    # If all APIs fail, return a random fallback quote
    try:
        random_quote = random.choice(fallback_quotes)
        return jsonify(random_quote)
    except Exception as e:
        return jsonify({
            "quote": "Every day is a new beginning. Take a deep breath and start again.",
            "author": "Unknown"
        })