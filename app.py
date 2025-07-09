import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import datetime

# --- Налаштування Flask та бази даних ---
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- ТИМЧАСОВИЙ БЛОК: Створення таблиць при кожному запуску додатка ---
# Цей блок буде створювати таблиці, якщо вони не існують.
# *** УВАГА: ЦЕ ТИМЧАСОВЕ РІШЕННЯ. ПІСЛЯ УСПІШНОГО ЗАПУСКУ МЕСЕНДЖЕРА,
#     ЦЕЙ БЛОК КОДУ ПОТРІБНО ВИДАЛИТИ З app.py І ЗРОБИТИ ЩЕ ОДИН КОМІТ/ПУШ. ***
with app.app_context():
    print("Attempting to create database tables...")
    db.create_all()
    print("Database tables creation process completed.")
# --- КІНЕЦЬ ТИМЧАСОВОГО БЛОКУ ---


# --- Модель даних (залишається без змін) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return '<User %r>' % self.username

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.now)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

    def __repr__(self):
        return f'<Message from {self.sender.username} to {self.receiver.username}: {self.message_text}>'

# --- Налаштування Flask-SocketIO (залишається без змін) ---
socketio = SocketIO(app)

online_users = {}
user_to_sid = {}
sid_to_user = {}


# --- Маршрути Flask (залишаються без змін) ---
@app.route('/')
def index():
    if 'username' in request.cookies:
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

@app.route('/chat')
def chat():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

@app.route('/logout')
def logout():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

# --- Обробники подій Socket.IO (залишаються без змін) ---
@socketio.on('connect')
def handle_connect():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

@socketio.on('disconnect')
def handle_disconnect():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

@socketio.on('send_message')
def handle_send_message(data):
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

def get_online_users_list():
    # ... (ваш код)
    pass # Залиште ваш існуючий код тут

# --- Запуск Сервера (змінений блок) ---
if __name__ == '__main__':
    # Рядок db.create_all() ПЕРЕНЕСЕНО вище!
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)