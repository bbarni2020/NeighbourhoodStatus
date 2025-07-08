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

app = Flask(__name__)
CORS(app)

slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)
handler = SlackRequestHandler(slack_app)

TRACKED_USERS_FILE = 'tracked_users.json'

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

@app.route('/status/<slack_real_id>', methods=['GET'])
def get_status(slack_real_id):
    try:
        response = requests.get('https://adventure-time.hackclub.dev/api/getYSWSSubmissions')
        response.raise_for_status()
        
        data = response.json()
        submissions = data.get('submissions', [])
        
        for submission in submissions:
            if submission.get('slackRealId') and slack_real_id in submission['slackRealId']:
                return jsonify({'status': submission.get('status', 'Unknown')})
        
        return jsonify({'error': 'User not found'}), 404
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Failed to fetch submissions'}), 500

def get_user_submission_status(slack_real_id):
    try:
        response = requests.get('https://adventure-time.hackclub.dev/api/getYSWSSubmissions')
        response.raise_for_status()
        
        data = response.json()
        submissions = data.get('submissions', [])
        
        for submission in submissions:
            if submission.get('slackRealId') and slack_real_id in submission['slackRealId']:
                return submission.get('status', 'Unknown')
        
        return None
    except requests.exceptions.RequestException:
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
                slack_app.client.chat_postMessage(
                    channel=user_data['channel'],
                    text=f"🔄 Your submission status has changed from *{user_data['last_status']}* to *{current_status}*"
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
        tracked_users[user_id] = {
            'channel': channel,
            'last_status': current_status
        }
        save_tracked_users()
        say(f"✅ Now tracking your submission status! Current status: *{current_status}*\nI'll notify you every time it changes.")
        print(f"Started tracking user {user_id} with status: {current_status}")
    else:
        say("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/track")
def handle_track_command(ack, respond, command):
    ack()
    user_id = command['user_id']
    channel = command['channel_id']
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        tracked_users[user_id] = {
            'channel': channel,
            'last_status': current_status
        }
        save_tracked_users()
        respond(f"✅ Now tracking your submission status! Current status: *{current_status}*\nI'll notify you every time it changes.")
        print(f"Started tracking user {user_id} with status: {current_status}")
    else:
        respond("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/status")
def handle_status_command(ack, respond, command):
    ack()
    user_id = command['user_id']
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        respond(f"📊 Your current submission status: *{current_status}*")
    else:
        respond("❌ Could not find your submission. Make sure you have submitted to YSWS.")

@slack_app.command("/untrack")
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
        respond(f"📋 Currently tracking {user_count} user(s):\n" + 
               "\n".join([f"• <@{uid}>: {data['last_status']}" for uid, data in tracked_users.items()]))
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
