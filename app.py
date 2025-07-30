from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, request, redirect, url_for, session,
    render_template, flash, jsonify
)
from functools import wraps
from datetime import datetime, timezone, timedelta
import json
import random

# --- 1. Import from your central setup files ---
from firebase_setup import database, auth
from api_routes import api

# --- App Initialization ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'super-secret-key'

# Register the API blueprint
app.register_blueprint(api, url_prefix='/api')


# --- Decorators and Helper Functions ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def parse_firebase_error(e):
    try:
        error_data = json.loads(e.args[1])
        message = error_data['error']['message']
        return {
            "EMAIL_NOT_FOUND": "Email not found.",
            "INVALID_PASSWORD": "Wrong password.",
            "EMAIL_EXISTS": "Email already in use.",
            "WEAK_PASSWORD": "Password too weak."
        }.get(message, message.replace('_', ' ').capitalize())
    except Exception:
        return "Authentication failed."


# --- USER-FACING HTML ROUTES ---

@app.route('/', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/signup', methods=['GET'])
def signup_page():
    return render_template('signup.html')

@app.route('/home', methods=['GET'])
@login_required
def home_page():
    return render_template('home.html')

@app.route('/entries', methods=['GET'])
@login_required
def entries_page():
    user_id = session['user_id']
    all_entries = database.child("entries").get(token=session['id_token'])
    user_entries = []
    if all_entries.each():
        for entry in all_entries.each():
            data = entry.val()
            if data.get('uid') == user_id and not data.get('is_hidden', False):
                data['id'] = entry.key()
                user_entries.append(data)
    user_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('entries.html', entries=user_entries)

@app.route('/new_entry', methods=['GET'])
@login_required
def new_entry_page():
    return render_template('new_entry.html')

@app.route('/edit_entry/<entry_id>', methods=['GET'])
@login_required
def edit_entry_page(entry_id):
    return render_template('edit_entry.html', entry_id=entry_id)

@app.route('/habits', methods=['GET'])
@login_required
def habits_page():
    user_id = session['user_id']
    all_habits = database.child("habits").get(token=session['id_token'])
    user_habits = []
    if all_habits.each():
        for habit in all_habits.each():
            data = habit.val()
            if data.get('user_id') == user_id:
                habit_dict = data.copy()
                habit_dict['id'] = habit.key()
                user_habits.append(habit_dict)
    return render_template('habits.html', habits=user_habits)

@app.route('/moods', methods=['GET'])
@login_required
def moods_page():
    user_id = session['user_id']
    all_moods_raw = database.child("moods").get(token=session['id_token'])
    all_logs = []
    if all_moods_raw.each():
        for log in all_moods_raw.each():
            data = log.val()
            if data.get('user_id') == user_id:
                data['id'] = log.key()
                data['timestamp_obj'] = datetime.fromisoformat(data['timestamp'])
                all_logs.append(data)
    all_logs.sort(key=lambda x: x['timestamp_obj'], reverse=True)
    today = datetime.now(timezone.utc)
    thirty_days_ago = today - timedelta(days=30)
    recent_logs = [log for log in all_logs if log['timestamp_obj'] >= thirty_days_ago]
    recent_logs.sort(key=lambda x: x['timestamp_obj'])
    graph_labels = [log['timestamp_obj'].strftime('%b %d') for log in recent_logs]
    graph_data = [log['mood_score'] for log in recent_logs]
    return render_template(
        'moods.html',
        all_logs=all_logs,
        graph_labels_json=json.dumps(graph_labels),
        graph_data_json=json.dumps(graph_data)
    )

@app.route('/daily_quote')
@login_required
def daily_quote_page():
    return render_template('quote.html')

# --- NEW: Routes for Hidden Entries Feature ---
@app.route('/verify_password', methods=['GET'])
@login_required
def verify_password_page():
    next_url = request.args.get('next', url_for('home_page'))
    return render_template('verify_password.html', next_url=next_url)

@app.route('/hidden_entries', methods=['GET'])
@login_required
def hidden_entries_page():
    if not session.get('is_verified'):
        return redirect(url_for('verify_password_page', next=request.url))
    
    user_id = session['user_id']
    all_entries = database.child("entries").get(token=session['id_token'])
    hidden_entries = []
    if all_entries.each():
        for entry in all_entries.each():
            data = entry.val()
            if data.get('uid') == user_id and data.get('is_hidden', False):
                data['id'] = entry.key()
                hidden_entries.append(data)
    hidden_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    session.pop('is_verified', None)
    return render_template('hidden_entries.html', entries=hidden_entries)


# --- AUTHENTICATION & DATA HANDLING POST ROUTES ---

@app.route('/', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        session['user_id'] = user['localId']
        session['email'] = email
        session['id_token'] = user.get('idToken')
        flash('Logged in successfully!', 'success')
        return redirect(url_for('home_page'))
    except Exception as e:
        flash(parse_firebase_error(e), 'error')
        return redirect(url_for('login_page'))

@app.route('/signup', methods=['POST'])
def signup():
    email = request.form.get('email')
    password = request.form.get('password')
    try:
        auth.create_user_with_email_and_password(email, password)
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login_page'))
    except Exception as e:
        flash(parse_firebase_error(e), 'error')
        return redirect(url_for('signup_page'))

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login_page'))

@app.route('/new_entry', methods=['POST'])
@login_required
def save_new_entry():
    uid = session['user_id']
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    mood = request.form.get('mood', 'none')
    is_hidden = 'is_hidden' in request.form

    if not title or not content:
        flash("Title and content cannot be empty.", "error")
        return redirect(url_for('new_entry_page'))
    
    timestamp = datetime.now(timezone.utc).isoformat()
    entry_data = {
        "uid": uid, "title": title, "content": content,
        "mood": mood, "timestamp": timestamp, "is_hidden": is_hidden
    }
    database.child("entries").push(entry_data, token=session['id_token'])
    
    if is_hidden:
        flash("Your private entry has been saved to your hidden journal!", "success")
        return redirect(url_for('hidden_entries_page'))
    else:
        flash("Journal entry saved successfully!", "success")
        return redirect(url_for('entries_page'))

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not name:
        flash('Habit name is required.', 'error')
        return redirect(url_for('habits_page'))
    habit_data = {
        "user_id": user_id, "name": name, "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(), "streak": 0, "completed_today": False
    }
    database.child("habits").push(habit_data, token=session['id_token'])
    flash('Habit added successfully!', 'success')
    return redirect(url_for('habits_page'))

@app.route('/log_mood', methods=['POST'])
@login_required
def log_mood():
    user_id = session['user_id']
    mood = request.form.get('mood')
    mood_score = request.form.get('mood_score')
    notes = request.form.get('notes', '').strip()
    timestamp = datetime.now(timezone.utc).isoformat()
    if not mood or not mood_score:
        flash('Please select a mood and score.', 'error')
        return redirect(url_for('moods_page'))
    mood_entry = {
        'user_id': user_id, 'mood': mood, 'mood_score': int(mood_score),
        'notes': notes, 'timestamp': timestamp
    }
    database.child('moods').push(mood_entry, token=session['id_token'])
    flash('Mood logged successfully!', 'success')
    return redirect(url_for('moods_page'))

@app.route('/verify_password', methods=['POST'])
@login_required
def verify_password():
    password = request.form.get('password')
    next_url = request.form.get('next_url', url_for('home_page'))
    user_email = session.get('email')
    try:
        auth.sign_in_with_email_and_password(user_email, password)
        session['is_verified'] = True
        flash('Verification successful!', 'success')
        return redirect(next_url)
    except Exception:
        flash('Incorrect password. Please try again.', 'error')
        return redirect(url_for('verify_password_page', next=next_url))

@app.route('/gratitude', methods=['GET'])
@login_required
def gratitude_page():
    """Displays a page with a random reflection prompt."""
    
    prompts = [
        "What is one small thing that brought you joy today?",
        "Describe a recent challenge you overcame and what you learned from it.",
        "Who is someone you're grateful for right now, and why?",
        "What is a quality you admire in yourself?",
        "Think of a favorite memory. What makes it so special to you?",
        "What are you looking forward to this week, no matter how small?",
        "Describe a moment today when you felt completely at peace.",
        "What skill are you glad to have?",
        "What is something beautiful you saw recently?"
    ]
    
    # Select one prompt at random to display
    random_prompt = random.choice(prompts)
    
    return render_template('gratitude.html', prompt=random_prompt)
@app.route('/about')
def about_page():
    """Renders the About Us page."""
    return render_template('about.html')

if __name__ == '__main__':
    # For production on Render
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)