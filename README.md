# Neighborhood YSWS Status Tracker 🚀 *(useless)*

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com)
[![Slack API](https://img.shields.io/badge/Slack-API-purple.svg)](https://api.slack.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)](https://github.com/bbarni2020/NeighbourhoodStatus)


**Unfortunately Neighborhood YSWS got cancelled - so this tool isn't useful anymore**

[![Message StatusBuddy on Slack](https://img.shields.io/badge/Message%20StatusBuddy%20on%20Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://hackclub.slack.com/team/U095F3Y7W3A)

A comprehensive Slack bot and web application for tracking Neighborhood YSWS database submission statuses with real-time notifications and AI-powered updates.

## Demo video of the Slack boz

<video controls>
  <source src="https://github.com/bbarni2020/NeighbourhoodStatus/raw/refs/heads/main/demo.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>

## ✨ Features

- **🔄 Real-time Status Tracking**: Automatically monitors submission status every 5 minutes
- **🔔 Instant Notifications**: Slack DM notifications when status changes
- **🤖 AI-Powered Messages**: Friendly, personalized status updates using AI
- **🌐 Web Dashboard**: Beautiful web interface for status monitoring
- **📱 Dual Login**: Support for both Slack OAuth and manual Slack ID entry
- **⚡ Live Updates**: Real-time status checking with caching for performance
- **🎨 Modern UI**: Responsive design with gradient backgrounds and smooth animations

## 🛠️ Tech Stack

- **Backend**: Python, Flask, Slack Bolt SDK
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Scheduling**: APScheduler for background tasks
- **APIs**: Slack Web API, Custom YSWS API
- **Styling**: Custom CSS with Tailwind-inspired utilities
- **Icons**: Font Awesome

## 📋 Prerequisites

- Python 3.8 or higher
- Slack workspace with bot permissions
- YSWS API access

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/NeighbourhoodStatus.git
cd NeighbourhoodStatus
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
Create a `.env` file in the root directory:
```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret
FLASK_SECRET_KEY=your-secret-key
```

### 4. Run the Application
```bash
python api.py
```

The application will be available at `http://localhost:8721`

## 📱 Usage

### Slack Bot Commands
- `/yswsdb-track` - Start tracking your submission status
- `/yswsdb-status` - Check your current status
- `/yswsdb-untrack` - Stop tracking notifications

### Web Interface
1. Visit the web interface at your deployment URL
2. Login using either:
   - **Slack OAuth**: Secure authentication through Slack
   - **Manual ID Entry**: Enter your Slack User ID directly
3. View your dashboard with real-time status updates
4. Enable/disable tracking as needed

### Finding Your Slack User ID
1. In Slack, click on your profile
2. Select "More" → "Copy member ID"
3. Use this ID for manual login

## 🎯 Status Types

| Status | Emoji | Description |
|--------|-------|-------------|
| **Pending** | 🕛 | Submission is waiting to be reviewed |
| **Approved** | 🟢 | Submission has been successfully approved |
| **Denied** | 🔴 | Submission has issues or hasn't been started |
| **Unknown** | ⚪ | Status is not recognized |

## 🔧 Configuration

### Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token | ✅ |
| `SLACK_SIGNING_SECRET` | Signing Secret for request verification | ✅ |
| `SLACK_CLIENT_ID` | OAuth Client ID | ✅ |
| `SLACK_CLIENT_SECRET` | OAuth Client Secret | ✅ |
| `FLASK_SECRET_KEY` | Flask session secret key | ✅ |

## 📁 Project Structure

```
NeighbourhoodStatus/
├── api.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── tracked_users.json     # User tracking data (auto-generated)
├── .env                   # Environment variables (create this)
├── static/
│   └── style.css         # Custom CSS styles
├── templates/
│   ├── base.html         # Base template
│   ├── login.html        # Login page
│   └── dashboard.html    # User dashboard
└── README.md             # This file
```

## 🔄 How It Works

1. **Status Monitoring**: The app checks the YSWS API every 5 minutes for status changes
2. **Change Detection**: Compares current status with last known status for each tracked user
3. **AI Messages**: Generates friendly status update messages using AI
4. **Slack Notifications**: Sends personalized DMs to users when their status changes
5. **Web Dashboard**: Provides real-time view of current status and tracking settings

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and commit: `git commit -m "Add feature"`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🐛 Issues & Support

- **Bug Reports**: [Create an issue](https://github.com/bbarni2020/NeighbourhoodStatus/issues)
- **Feature Requests**: [Start a discussion](https://github.com/bbarni2020/NeighbourhoodStatus/discussions)

## 🙏 Acknowledgments

- [Slack API](https://api.slack.com) for excellent documentation
- [Flask](https://flask.palletsprojects.com) for the web framework
- [Font Awesome](https://fontawesome.com) for beautiful icons
- [Hack Club](https://hackclub.com) for the YSWS program

---

<div align="center">
Made for the Neighborhood community
</div>
