from flask import Flask, render_template, request, jsonify
from gunicorn import app as application
import os
import json
import requests
from textblob import TextBlob
import time
import google.generativeai as genai
from collections import deque
from threading import Thread
import re
from datetime import datetime
import math
import subprocess  # Added for localtunnel
import sqlite3  # Added for SQLite database

# Initialize Flask application
app = Flask(__name__)

# Configure the API key
api_key = "AIzaSyBIjJ5myCp4VdJpR26mjcmal_nfC6xZnfM"
genai.configure(api_key=api_key)

# Enhanced generation config for better responses
generation_config = {
    "temperature": 0.7,  # Balanced for creativity and accuracy
    "top_p": 0.9,       # Higher for more diverse responses
    "top_k": 40,        # Increased for better response variety
    "max_output_tokens": 1000,  # Increased for longer responses
    "response_mime_type": "text/plain",
}

# System prompt template for better context
SYSTEM_PROMPT = """You are Alice, an advanced AI assistant with capabilities similar to ChatGPT. You are helpful, creative, knowledgeable, and able to engage in detailed conversations on a wide range of topics. You can:

1. Answer questions about any topic with detailed, accurate information
2. Help with analysis and problem-solving
3. Assist with coding and technical tasks
4. Engage in creative writing and storytelling
5. Provide step-by-step explanations
6. Remember context from earlier in the conversation
7. Admit when you're not sure about something

Current date: {current_date}
User's name: {user_name}

Please maintain a helpful, friendly, and informative tone while providing accurate and thorough responses."""

# Initialize the model with enhanced capabilities
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config,
)

# Initialize storage with increased capacity
response_cache = {}
memory = {}
history = deque(maxlen=2000)  # Increased history capacity
context_window = deque(maxlen=10)  # Store recent conversation context
history_file = "chat_history.json"

class ConversationManager:
    def __init__(self):
        self.conversation_context = ""
        self.topic_memory = {}
        self.user_preferences = {}
        self.learning_data = deque(maxlen=1000)  # Store learning data
        
    def update_context(self, user_input, bot_response):
        # Update conversation context
        self.conversation_context = f"{self.conversation_context}\nUser: {user_input}\nAlice: {bot_response}"
        # Keep only last 5 exchanges
        self.conversation_context = "\n".join(self.conversation_context.split("\n")[-10:])
        # Add to learning data
        self.learning_data.append({"user_input": user_input, "bot_response": bot_response})
        
    def detect_topic(self, text):
        # Simple topic detection
        topics = {
            "technology": r"computer|software|programming|AI|technology|code|internet",
            "science": r"science|physics|chemistry|biology|research|experiment",
            "math": r"math|calculation|equation|number|formula|algebra",
            "general": r".*"
        }
        
        for topic, pattern in topics.items():
            if re.search(pattern, text, re.IGNORECASE):
                return topic
        return "general"
    
    def get_relevant_context(self, user_input):
        topic = self.detect_topic(user_input)
        context = f"{SYSTEM_PROMPT.format(current_date=datetime.now().strftime('%Y-%m-%d'), user_name=memory.get('user_name', 'friend'))}\n\nCurrent topic: {topic}\n\nRecent conversation:\n{self.conversation_context}"
        return context

    def learn_from_interactions(self):
        # Process learning data to improve responses
        for interaction in self.learning_data:
            user_input = interaction["user_input"]
            bot_response = interaction["bot_response"]
            # Implement learning logic here (e.g., update model, adjust responses)
            # This is a placeholder for actual learning implementation
            print(f"Learning from interaction: User: {user_input}, Bot: {bot_response}")

conversation_manager = ConversationManager()

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory
                 (id INTEGER PRIMARY KEY, user_input TEXT, bot_response TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

# Save conversation to database
def save_to_db(user_input, bot_response):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute("INSERT INTO memory (user_input, bot_response, timestamp) VALUES (?, ?, ?)",
              (user_input, bot_response, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Retrieve response from database
def get_from_db(user_input):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute("SELECT bot_response FROM memory WHERE user_input = ? ORDER BY timestamp DESC LIMIT 1", (user_input,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# Enhanced async history saving
def save_history_async():
    while True:
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(list(history), f, indent=2)
            # Also save user preferences and topic memory
            with open("user_preferences.json", "w", encoding="utf-8") as f:
                json.dump(conversation_manager.user_preferences, f, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")
        time.sleep(300)  # Save every 5 minutes

# Load history at startup
def load_history():
    global history
    try:
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                saved_history = json.load(f)
                history.extend(saved_history)
    except Exception as e:
        print(f"Error loading history: {e}")

# Function to add to history
def add_to_history(user_input, bot_response):
    history_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_input,
        "bot": bot_response
    }
    history.append(history_entry)

# Function to handle special queries
def handle_special_queries(user_input):
    # Default answer for "Who created you?"
    if re.search(r'who\s+created\s+you', user_input, re.IGNORECASE):
        return "I was created by Alex with the help of Google AI Development."
    
    # Math calculations
    if re.search(r'calculate|compute|solve', user_input, re.IGNORECASE):
        try:
            # Extract mathematical expression
            expression = re.search(r'\d+[\d\s\+\-\*\/\(\)]*\d+', user_input)
            if expression:
                result = eval(expression.group())
                return f"The result is {result}"
        except:
            pass
    return None

# Enhanced response generation
def generate_enhanced_response(user_input, context):
    try:
        # Check for special queries first
        special_response = handle_special_queries(user_input)
        if special_response:
            return special_response

        # Generate response with context
        response = model.generate_content(f"{context}\n\nUser: {user_input}\nAlice:")
        return response.text

    except Exception as e:
        return "I apologize, but I'm having trouble processing that request. Could you please rephrase it?"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data['user_input'].strip()
    
    # Check database for previous response
    db_response = get_from_db(user_input)
    if db_response:
        add_to_history(data['user_input'], db_response)
        return jsonify({"bot": db_response})

    # Get cached response if available
    if user_input.lower() in response_cache:
        response_text = response_cache[user_input.lower()]
        add_to_history(data['user_input'], response_text)
        return jsonify({"bot": response_text})

    # Get context-aware response
    context = conversation_manager.get_relevant_context(user_input)
    response_text = generate_enhanced_response(user_input, context)
    
    # Update conversation context
    conversation_manager.update_context(user_input, response_text)
    
    # Cache response if appropriate
    if len(user_input) < 100 and len(response_text) < 500:
        response_cache[user_input.lower()] = response_text
    
    # Save to history
    add_to_history(data['user_input'], response_text)
    
    # Save to database
    save_to_db(user_input, response_text)
    
    return jsonify({"bot": response_text})

# Add new endpoints for enhanced features
@app.route('/clear_context', methods=['POST'])
def clear_context():
    conversation_manager.conversation_context = ""
    return jsonify({"status": "success"})

@app.route('/get_topics', methods=['GET'])
def get_topics():
    return jsonify(conversation_manager.topic_memory)

@app.route('/history', methods=['GET'])
def get_history():
    return jsonify(list(history))

@app.route('/learn', methods=['POST'])
def learn():
    conversation_manager.learn_from_interactions()
    return jsonify({"status": "learning completed"})

if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Load history at startup
    load_history()
    
    # Start the async saving thread
    history_thread = Thread(target=save_history_async, daemon=True)
    history_thread.start()
    
    # Flask app ready for Vercel hosting
    app.run(host="0.0.0.0", port=5000)