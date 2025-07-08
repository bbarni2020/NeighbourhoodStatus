from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import time
import threading
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
import atexit
from datetime import datetime, timedelta

def load_env_file():
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass

load_env_file()

app = Flask(__name__)
CORS(app)

slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

handler = SlackRequestHandler(slack_app)

TRACKED_USERS_FILE = 'tracked_users.json'
submissions_cache = {
    'data': None,
    'last_updated': None,
    'cache_duration': timedelta(minutes=2)
}

def load_tracked_users():
    try:
        with open(TRACKED_USERS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_tracked_users():
    try:
        with open(TRACKED_USERS_FILE, 'w') as f:
            json.dump(tracked_users, f, indent=2)
    except Exception as e:
        print(f"Error saving tracked users: {e}")

tracked_users = load_tracked_users()
scheduler = BackgroundScheduler()
scheduler.start()

atexit.register(save_tracked_users)

def get_cached_submissions():
    now = datetime.now()
    if (submissions_cache['data'] is None or 
        submissions_cache['last_updated'] is None or 
        now - submissions_cache['last_updated'] > submissions_cache['cache_duration']):
        
        try:
            print("Fetching fresh data from API...")
            response = requests.get('https://adventure-time.hackclub.dev/api/getYSWSSubmissions')
            response.raise_for_status()
            
            submissions_cache['data'] = response.json()
            submissions_cache['last_updated'] = now
            print(f"Cache updated at {now}")
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching submissions: {e}")
            if submissions_cache['data'] is None:
                return None
    else:
        print("Using cached data")
    
    return submissions_cache['data']

@app.route('/status/<slack_real_id>', methods=['GET'])
def get_status(slack_real_id):
    try:
        data = get_cached_submissions()
        if data is None:
            return jsonify({'error': 'Failed to fetch submissions'}), 500
            
        submissions = data.get('submissions', [])
        
        for submission in submissions:
            if submission.get('slackRealId') and slack_real_id in submission['slackRealId']:
                status = submission.get('status', 'Unknown')
                emoji, status_name, description = get_status_emoji_and_description(status)
                return jsonify({
                    'status': status_name,
                    'emoji': emoji,
                    'status_name': status_name,
                    'description': description
                })
        
        return jsonify({'error': 'User not found'}), 404
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch submissions'}), 500

def get_status_emoji_and_description(status):
    if status.startswith("1–"):
        return "🟡", "Pending Submission", "Your submission is waiting to be reviewed"
    elif status.startswith("2–"):
        return "🟢", "Approved", "Your submission has been successfully submitted"
    elif status.startswith("0–"):
        return "🔴", "Denied", "Your submission has not been started or there's an issue"
    else:
        return "⚪", "Unknown", "Status is not recognized"

def get_ai_message(status_name, old_status=None):
    try:
        if status_name == "Pending Submission":
            if old_status:
                prompt = f"Write a short casual buddy message for someone whose YSWS submission changed from '{old_status}' to 'Pending Submission'. Keep it simple and friend-like."
            else:
                prompt = f"Write a short casual buddy message for someone whose YSWS submission is 'Pending Submission'. Keep it simple and friend-like."
        elif status_name == "Approved":
            if old_status:
                prompt = f"Write a short casual buddy congratulations message for someone whose YSWS submission changed from '{old_status}' to 'Approved'! Keep it simple and friend-like."
            else:
                prompt = f"Write a short casual buddy congratulations message for someone whose YSWS submission is 'Approved'! Keep it simple and friend-like."
        elif status_name == "Denied":
            if old_status:
                prompt = f"Write a short casual buddy message for someone whose YSWS submission changed from '{old_status}' to 'Denied'. Be supportive but realistic. Keep it simple and friend-like."
            else:
                prompt = f"Write a short casual buddy message for someone whose YSWS submission is 'Denied'. Be supportive but realistic. Keep it simple and friend-like."
        else:
            prompt = f"Something went wrong with the status update. Please check the status name: {status_name}. Write a short casual buddy message about a YSWS submission status update. Keep it simple and friend-like. It has been '{old_status}' before."

        response = requests.post(
            'https://ai.hackclub.com/chat/completions',
            headers={'Content-Type': 'application/json'},
            json={
                'messages': [
                    {'role': 'system', 'content': 'You are a casual buddy messaging a friend. Write only plain text with no formatting, markdown, quotes, or extra explanation. Just write the message directly as you would text a friend.'},
                    {'role': 'user', 'content': prompt}
                ]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            ai_data = response.json()
            if 'choices' in ai_data and len(ai_data['choices']) > 0:
                return ai_data['choices'][0]['message']['content'].strip()
    
    except Exception as e:
        print(f"Error getting AI message: {e}")
    
    fallback_messages = {
        "Pending Submission": "⏳ Still waiting on the review team, huh? They're probably just taking their time to appreciate your work �",
        "Approved": "🎉 Yooo, you got approved! Nice work buddy! 🚀",
        "Denied": "� Ah man, that's a bummer. But hey, happens to the best of us! Time to regroup and try again �"
    }
    
    return fallback_messages.get(status_name, "📱 Got an update on your submission! Let's see what's up 👀")

def get_user_submission_status(slack_real_id):
    try:
        data = get_cached_submissions()
        if data is None:
            return None
            
        submissions = data.get('submissions', [])
        
        for submission in submissions:
            if submission.get('slackRealId') and slack_real_id in submission['slackRealId']:
                return submission.get('status', 'Unknown')
        
        return None
    except Exception:
        return None

def check_status_changes():
    print(f"Checking status changes for {len(tracked_users)} users...")
    
    for user_id, user_data in list(tracked_users.items()):
        current_status = get_user_submission_status(user_id)
        
        if current_status is None:
            print(f"Could not fetch status for user {user_id}")
            continue
            
        if current_status != user_data['last_status']:
            try:
                emoji, status_name, description = get_status_emoji_and_description(current_status)
                old_emoji, old_status_name, _ = get_status_emoji_and_description(user_data['last_status'])
                ai_message = get_ai_message(status_name, user_data['last_status'])
                
                slack_app.client.chat_postMessage(
                    channel=user_id,
                    text=f"{ai_message}\n\n"
                        f"🔄 **Status Update Alert**\n\n"
                        f"Your YSWS submission status has changed!\n"
                        f"**Current Status:** {emoji} *{status_name}*\n\n"
                        f"💬 **Description:** {description}"
                )
                tracked_users[user_id]['last_status'] = current_status
                save_tracked_users()
                print(f"Status updated for user {user_id}: {user_data['last_status']} -> {current_status}")
            except Exception as e:
                print(f"Error sending message to {user_id}: {e}")
        else:
            print(f"No status change for user {user_id}: {current_status}")

scheduler.add_job(check_status_changes, 'interval', minutes=5)

@slack_app.message("track status")
def handle_track_status(message, say):
    user_id = message['user']
    channel = message['channel']
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        tracked_users[user_id] = {
            'channel': channel,
            'last_status': current_status
        }
        save_tracked_users()
        say(f"✅ **YSWS Submission Tracking Activated**\n\n"
            f"📊 **Current Status:** {emoji} *{status_name}*\n"
            f"💬 {description}\n\n"
            f"⏰ **Check Interval:** Every 5 minutes\n"
            f"🔔 **Notifications:** Direct messages when status changes\n"
            f"🛑 **To stop tracking:** Use `/untrack` command\n\n"
            f"I'll monitor your submission and notify you immediately when your status changes!")
        print(f"Started tracking user {user_id} with status: {current_status}")
    else:
        say("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/yswsdb-track")
def handle_track_command(ack, respond, command):
    ack()
    user_id = command['user_id']
    channel = command['channel_id']
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        tracked_users[user_id] = {
            'channel': channel,
            'last_status': current_status
        }
        save_tracked_users()
        respond(f"✅ *YSWS Submission Tracking Activated*\n\n"
               f"📊 *Current Status:* {emoji} {status_name}\n"
               f"📋 *Status Type:* {status_name}\n"
               f"💬 *Description:* {description}\n\n"
               f"👤 *User ID:* {user_id}\n"
               f"📱 *Channel:* <#{channel}>\n"
               f"⏰ *Check Interval:* Every 5 minutes\n"
               f"🔔 *Notifications:* Direct messages when status changes\n"
               f"🛑 *To stop tracking:* Use `/untrack` command\n\n"
               f"I'll monitor your submission and notify you immediately when your status changes!")
        print(f"Started tracking user {user_id} with status: {current_status}")
    else:
        respond("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/yswsdb-status")
def handle_status_command(ack, respond, command):
    ack()
    user_id = command['user_id']
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        respond(f"📊 **Your Current YSWS Submission Status**\n\n"
               f"{emoji} **Status:** *{current_status}*\n"
               f"📋 **Type:** {status_name}\n"
               f"💬 **Description:** {description}")
    else:
        respond("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/yswsdb-untrack")
def handle_untrack_command(ack, respond, command):
    ack()
    user_id = command['user_id']
    
    if user_id in tracked_users:
        del tracked_users[user_id]
        save_tracked_users()
        respond("🔕 Stopped tracking your submission status.")
        print(f"Stopped tracking user {user_id}")
    else:
        respond("❌ You are not currently being tracked.")

@slack_app.command("/list")
def handle_list_command(ack, respond, command):
    ack()
    
    if tracked_users:
        user_count = len(tracked_users)
        user_list = []
        for uid, data in tracked_users.items():
            emoji, status_name, _ = get_status_emoji_and_description(data['last_status'])
            user_list.append(f"• <@{uid}>: {emoji} {data['last_status']}")
        
        respond(f"📋 **Currently tracking {user_count} user(s):**\n\n" + "\n".join(user_list))
    else:
        respond("📋 No users are currently being tracked.")

@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == '__main__':
    print(f"Starting bot with {len(tracked_users)} tracked users loaded from file")
    for user_id, data in tracked_users.items():
        print(f"  - User {user_id}: {data['last_status']}")
    app.run(host='0.0.0.0', port=8721, debug=False)