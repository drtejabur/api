import json
import requests
import logging
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import firebase_admin
from firebase_admin import credentials, db
import os
import traceback

# Set up logging for better debugging in production
logging.basicConfig(level=logging.INFO)

# Initialize Flask app
app = Flask(__name__)

# Path to your service account key file
SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE', './service-account.json')

# Initialize Firebase Admin SDK with the credentials
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.getenv('DATABASE_URL', 'https://healthmeet-f4b64-default-rtdb.firebaseio.com/')
    })
    logging.info('Firebase initialized successfully.')
except Exception as e:
    logging.error(f"Error initializing Firebase: {str(e)}")
    raise e

# Define the required scopes for Firebase Cloud Messaging (FCM)
SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

# Function to get access token for FCM
def get_access_token():
    try:
        credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        logging.error(f"Error fetching access token: {str(e)}")
        raise e

# Function to check user status in Firebase Realtime Database
def check_user_status(user_id):
    try:
        ref = db.reference(f'/users/{user_id}/-status')
        status = ref.get()
        logging.info(f"User {user_id} status: {status}")
        return status
    except Exception as e:
        logging.error(f"Error checking user status: {str(e)}")
        traceback.print_exc()
        return None

# Function to get device token from Firebase Realtime Database under the 'token' key
def get_device_token(user_id):
    try:
        ref = db.reference(f'/users/{user_id}/token')
        device_token = ref.get()
        logging.info(f"User {user_id} device_token: {device_token}")
        return device_token
    except Exception as e:
        logging.error(f"Error fetching device token: {str(e)}")
        traceback.print_exc()
        return None

# Function to send FCM notification
def send_fcm_notification(device_token, title, body):
    try:
        access_token = get_access_token()
        url = 'https://fcm.googleapis.com/v1/projects/healthmeet-f4b64/messages:send'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            "message": {
                "token": device_token,
                "notification": {
                    "title": title,
                    "body": body
                }
            }
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)  # 10-second timeout
        logging.info(f"FCM Response: {response.status_code}, {response.text}")
        if response.status_code == 200:
            return {'status': 'success', 'message': 'Notification sent successfully!'}
        else:
            return {'status': 'error', 'message': response.text}
    except requests.exceptions.Timeout:
        logging.error("Timeout error while sending FCM notification.")
        return {'status': 'error', 'message': 'Timeout while sending notification.'}
    except Exception as e:
        logging.error(f"Error sending notification: {str(e)}")
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}

# API route to send FCM notification if user is offline
@app.route('/send_notification', methods=['GET'])
def send_notification():
    try:
        # Get the query parameters from the URL
        title = request.args.get('title')
        body = request.args.get('body')
        user_id = request.args.get('user_id')  # User ID for checking status and fetching device token

        # Validate inputs
        if not title or not body or not user_id:
            return jsonify({'status': 'error', 'message': 'Missing title, body, or user_id'}), 400

        logging.info(f"Received request for user_id: {user_id}")

        # Check user's status
        user_status = check_user_status(user_id)
        if user_status is None:
            return jsonify({'status': 'error', 'message': 'Failed to check user status'}), 500

        if user_status == 'online':
            return jsonify({'status': 'info', 'message': 'User is online, notification not sent.'})

        # Fetch the user's device token from Firebase
        device_token = get_device_token(user_id)
        if not device_token:
            return jsonify({'status': 'error', 'message': 'Device token not found for user'}), 500

        # If the user is offline, send FCM notification
        result = send_fcm_notification(device_token, title, body)
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error in send_notification route: {str(e)}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Starting the Flask application
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
