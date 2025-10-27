# Add this code to the TOP of your musicbot.py file

from flask import Flask
from threading import Thread

# Simple health check server for Fly.io
app = Flask('')

@app.route('/')
def home():
    return "Discord Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()

# Start the health check server
keep_alive()

# YOUR EXISTING BOT CODE STARTS BELOW THIS LINE