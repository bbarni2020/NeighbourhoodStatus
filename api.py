from flask import Flask, jsonify, request, render_template, redirect, url_for, session
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
import secrets

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
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN environment variable is required")
if not SLACK_SIGNING_SECRET:
    raise ValueError("SLACK_SIGNING_SECRET environment variable is required")

slack_app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
    process_before_response=True
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
        return "🕛", "Pending Submission", "Your submission is waiting to be reviewed"
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

                delete_bot_messages_in_dm(slack_app.client, user_id)
                
                slack_app.client.chat_postMessage(
                    channel=user_id,
                    text=f"{ai_message}\n\n"
                        f"🔄 *Status Update Alert*\n\n"
                        f"Your YSWS submission status has changed!\n"
                        f"*Current Status:* {emoji} {status_name}\n\n"
                        f"💬 *Description:* {description}\n\n"
                        f"*Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} UTC"
                )
                tracked_users[user_id]['last_status'] = current_status
                tracked_users[user_id]['last_updated'] = datetime.now().isoformat()
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
            'last_status': current_status,
            'last_updated': datetime.now().isoformat()
        }
        save_tracked_users()
        try:
            delete_bot_messages_in_dm(slack_app.client, user_id)
            
            slack_app.client.chat_postMessage(
                channel=user_id,
                text=f"✅ *YSWS Submission Tracking Started*\n\n"
                     f"📊 *Current Status:* {emoji} {status_name}\n"
                     f"💬 *Description:* {description}\n\n"
                     f"⏰ *Check Interval:* Every 5 minutes\n"
                     f"🔔 *Notifications:* You'll receive updates here when your status changes\n"
                     f"🛑 *To stop tracking:* Use `/yswsdb-untrack` command\n\n"
                     f"*Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} UTC\n\n"
                     f"I'll monitor your submission and notify you immediately when your status changes!"
            )
        except Exception as e:
            print(f"Error sending DM to {user_id}: {e}")
        
        say(f"✅ *YSWS Submission Tracking Activated*\n\n"
            f"📊 *Current Status:* {emoji} {status_name}\n"
            f"💬 {description}\n\n"
            f"⏰ *Check Interval:* Every 5 minutes\n"
            f"🔔 *Notifications:* Direct messages when status changes\n"
            f"🛑 *To stop tracking:* Use `/untrack` command\n\n"
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
            'last_status': current_status,
            'last_updated': datetime.now().isoformat()
        }
        save_tracked_users()
        try:
            delete_bot_messages_in_dm(slack_app.client, user_id)
            
            slack_app.client.chat_postMessage(
                channel=user_id,
                text=f"✅ *YSWS Submission Tracking Started*\n\n"
                     f"📊 *Current Status:* {emoji} {status_name}\n"
                     f"💬 *Description:* {description}\n\n"
                     f"⏰ *Check Interval:* Every 5 minutes\n"
                     f"🔔 *Notifications:* You'll receive updates here when your status changes\n"
                     f"🛑 *To stop tracking:* Use `/yswsdb-untrack` command\n\n"
                     f"*Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} UTC\n\n"
                     f"I'll monitor your submission and notify you immediately when your status changes!"
            )
        except Exception as e:
            print(f"Error sending DM to {user_id}: {e}")
        
        respond(f"✅ *YSWS Submission Tracking Activated*\n\n"
               f"📊 *Current Status:* {emoji} {status_name}\n"
               f"📋 *Status Type:* {status_name}\n"
               f"💬 *Description:* {description}\n\n"
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
        respond(f"📊 *Your Current YSWS Submission Status*\n\n"
               f"{emoji} *Status:* {current_status}\n"
               f"📋 *Type:* {status_name}\n"
               f"💬 *Description:* {description}")
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
        
        respond(f"📋 *Currently tracking {user_count} user(s):*\n\n" + "\n".join(user_list))
    else:
        respond("📋 No users are currently being tracked.")

@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

@slack_app.event("app_home_opened")
def update_home_tab(client, event, logger):
    try:
        user_id = event["user"]

        is_tracked = user_id in tracked_users
        current_status = get_user_submission_status(user_id)

        status_text = ""
        if is_tracked and current_status:
            emoji, status_name, description = get_status_emoji_and_description(current_status)
            last_updated = tracked_users[user_id].get('last_updated', 'Unknown')
            if last_updated != 'Unknown':
                formatted_time = last_updated[:19].replace('T', ' ') + ' UTC'
            else:
                formatted_time = 'Unknown'
            status_text = f"\n\n📊 *Current Status:* {emoji} {status_name}\n💬 {description}\n🕐 *Last Updated:* {formatted_time}"
        
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Welcome to YSWS Status Tracker!* 🏠\n\nTrack your submission status and get notified of changes automatically.{status_text}"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Quick Actions:*"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔔 Start Tracking" if not is_tracked else "🔄 Refresh Status"
                                },
                                "action_id": "start_tracking",
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📊 Check Status"
                                },
                                "action_id": "check_status"
                            }
                        ]
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔕 Stop Tracking"
                                },
                                "action_id": "stop_tracking",
                                "style": "danger"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "❓ Help"
                                },
                                "action_id": "show_help"
                            }
                        ]
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 *Tip: You can also use slash commands like `/yswsdb-track` in any channel*"
                            }
                        ]
                    }
                ]
            }
        )
    except Exception as e:
        print(f"Error publishing home tab: {e}")

@slack_app.action("start_tracking")
def handle_start_tracking_button(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        tracked_users[user_id] = {
            'channel': user_id,
            'last_status': current_status,
            'last_updated': datetime.now().isoformat()
        }
        save_tracked_users()

        delete_bot_messages_in_dm(client, user_id)

        client.chat_postMessage(
            channel=user_id,
            text=f"✅ *YSWS Submission Tracking Started*\n\n"
                 f"📊 *Current Status:* {emoji} {status_name}\n"
                 f"💬 *Description:* {description}\n\n"
                 f"⏰ *Check Interval:* Every 5 minutes\n"
                 f"🔔 *Notifications:* You'll receive updates here when your status changes\n"
                 f"🛑 *To stop tracking:* Use `/yswsdb-untrack` command\n\n"
                 f"*Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                 f"I'll monitor your submission and notify you immediately when your status changes!"
        )

        update_home_tab(client, {"user": user_id}, print)
        
    else:
        delete_bot_messages_in_dm(client, user_id)
        
        client.chat_postMessage(
            channel=user_id,
            text="❌ Could not find your submission. Make sure you have submitted to YSWS."
        )

@slack_app.action("check_status")
def handle_check_status_button(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        
        delete_bot_messages_in_dm(client, user_id)
        
        client.chat_postMessage(
            channel=user_id,
            text=f"📊 *Your Current YSWS Submission Status*\n\n"
                 f"{emoji} *Status:* {status_name}\n"
                 f"💬 *Description:* {description}\n\n"
                 f"*Checked:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
    else:
        delete_bot_messages_in_dm(client, user_id)
        
        client.chat_postMessage(
            channel=user_id,
            text="❌ Could not find your submission. Make sure you have submitted to YSWS."
        )

@slack_app.action("stop_tracking")
def handle_stop_tracking_button(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    
    if user_id in tracked_users:
        del tracked_users[user_id]
        save_tracked_users()
        
        delete_bot_messages_in_dm(client, user_id)
        
        client.chat_postMessage(
            channel=user_id,
            text="🔕 *Tracking stopped!* You won't receive status update notifications anymore."
        )

        update_home_tab(client, {"user": user_id}, print)
        
    else:
        delete_bot_messages_in_dm(client, user_id)
        
        client.chat_postMessage(
            channel=user_id,
            text="❌ You're not currently being tracked."
        )

@slack_app.action("show_help")
def handle_help_button(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    
    delete_bot_messages_in_dm(client, user_id)
    
    client.chat_postMessage(
        channel=user_id,
        text="*YSWS Status Tracker Help* 📚\n\n"
             "*Available Commands:*\n"
             "• `/yswsdb-track` - Start tracking\n"
             "• `/yswsdb-status` - Check current status\n"
             "• `/yswsdb-untrack` - Stop tracking\n\n"
             "*Features:*\n"
             "• Automatic status checking every 5 minutes\n"
             "• Direct message notifications on changes\n"
             "• AI-powered friendly status updates\n"
             "• Interactive buttons in bot profile\n\n"
             "*Status Types:*\n"
             "• 🕛 Pending - Waiting for review\n"
             "• 🟢 Approved - Successfully submitted\n"
             "• 🔴 Denied - Issues or not started\n\n"
             "*Need help?* Contact your YSWS administrator."
    )

def delete_bot_messages_in_dm(client, user_id):
    """Delete previous bot messages in a DM channel with a user"""
    try:
        bot_info = client.auth_test()
        bot_user_id = bot_info["user_id"]
        
        response = client.conversations_history(
            channel=user_id,
            limit=100
        )
        
        if response["ok"]:
            messages = response["messages"]
            
            for message in messages:
                if message.get("user") == bot_user_id:
                    try:
                        client.chat_delete(
                            channel=user_id,
                            ts=message["ts"]
                        )
                    except Exception as e:
                        print(f"Could not delete message {message['ts']}: {e}")
                        
    except Exception as e:
        print(f"Error deleting bot messages for user {user_id}: {e}")

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# OAuth routes commented out - using manual login only
# @app.route('/login')
# def login():
#     client_id = os.environ.get("SLACK_CLIENT_ID")
#     
#     redirect_uri = request.url_root.replace('http://', 'https://') + 'auth/callback'
#     redirect_uri = redirect_uri.rstrip('/')
#     if not redirect_uri.endswith('/auth/callback'):
#         redirect_uri += '/auth/callback'
#     
#     scope = 'openid,profile'
#     
#     slack_auth_url = f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}"
#     return redirect(slack_auth_url)

# @app.route('/auth/callback')
# def auth_callback():
#     code = request.args.get('code')
#     if not code:
#         return redirect(url_for('index'))
#     
#     client_id = os.environ.get("SLACK_CLIENT_ID")
#     client_secret = os.environ.get("SLACK_CLIENT_SECRET")
#     redirect_uri = request.url_root + 'auth/callback'
#     
#     response = requests.post('https://slack.com/api/oauth.v2.access', data={
#         'client_id': client_id,
#         'client_secret': client_secret,
#         'code': code,
#         'redirect_uri': redirect_uri
#     })
#     
#     data = response.json()
#     if data.get('ok'):
#         user_info = data['authed_user']
#         session['user_id'] = user_info['id']
#         session['access_token'] = user_info['access_token']
#     
#     return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    # OAuth user info fetching commented out - using manual login only
    # access_token = session.get('access_token')
    is_manual_login = session.get('manual_login', False)
    
    # if access_token and not is_manual_login and ('user_name' not in session or 'user_image' not in session):
    #     user_details = requests.get('https://slack.com/api/users.identity', 
    #                               headers={'Authorization': f"Bearer {access_token}"})
    #     user_data = user_details.json()
    #     
    #     if user_data.get('ok'):
    #         session['user_name'] = user_data['user']['name']
    #         session['user_email'] = user_data['user'].get('email', '')
    #         session['user_image'] = user_data['user']['image_192']
    
    current_status = get_user_submission_status(user_id)
    is_tracked = user_id in tracked_users
    
    status_info = None
    if current_status:
        emoji, status_name, description = get_status_emoji_and_description(current_status)
        status_info = {
            'emoji': emoji,
            'name': status_name,
            'description': description,
            'raw_status': current_status
        }
    
    tracking_info = None
    if is_tracked:
        tracking_data = tracked_users[user_id]
        last_updated = tracking_data.get('last_updated', 'Unknown')
        if last_updated != 'Unknown':
            formatted_time = last_updated[:19].replace('T', ' ') + ' UTC'
        else:
            formatted_time = 'Unknown'
        tracking_info = {
            'last_updated': formatted_time,
            'check_interval': '5 minutes'
        }
    
    return render_template('dashboard.html', 
                         user_name=session.get('user_name', 'User'),
                         user_image=session.get('user_image', ''),
                         status_info=status_info,
                         is_tracked=is_tracked,
                         tracking_info=tracking_info,
                         is_manual_login=is_manual_login)

@app.route('/api/track', methods=['POST'])
def api_track():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    current_status = get_user_submission_status(user_id)
    
    if current_status:
        tracked_users[user_id] = {
            'channel': user_id,
            'last_status': current_status,
            'last_updated': datetime.now().isoformat()
        }
        save_tracked_users()
        return jsonify({'success': True, 'message': 'Tracking started successfully'})
    else:
        return jsonify({'error': 'Submission not found'}), 404

@app.route('/api/untrack', methods=['POST'])
def api_untrack():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    if user_id in tracked_users:
        del tracked_users[user_id]
        save_tracked_users()
        return jsonify({'success': True, 'message': 'Tracking stopped successfully'})
    else:
        return jsonify({'error': 'Not currently tracked'}), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/manual-login', methods=['POST'])
def manual_login():
    slack_id = request.form.get('slack_id', '').strip()
    
    if not slack_id:
        return redirect(url_for('index'))
    
    current_status = get_user_submission_status(slack_id)
    
    if current_status:
        session['user_id'] = slack_id
        session['user_name'] = f'User-{slack_id[:8]}'
        session['user_image'] = ''
        session['manual_login'] = True
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', error=f'No submission found for Slack ID: {slack_id}')

if __name__ == '__main__':
    print(f"Starting bot with {len(tracked_users)} tracked users loaded from file")
    for user_id, data in tracked_users.items():
        print(f"  - User {user_id}: {data['last_status']}")
    app.run(host='0.0.0.0', port=8721, debug=False)