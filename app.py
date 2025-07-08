from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)

# Отримання SECRET_KEY зі змінних середовища для продакшену, або генеруємо для розробки
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(24) 

# Конфігурація бази даних:
# Використовуємо DATABASE_URL, якщо вона встановлена (наприклад, Heroku Postgres),
# інакше використовуємо SQLite для локальної розробки.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')

# Якщо використовуємо PostgreSQL з Heroku, URI може починатися з 'postgres://', 
# що SQLAlchemy не розпізнає як 'postgresql://'.
# Тому замінюємо префікс для сумісності.
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 

db = SQLAlchemy(app)

# Налаштовуємо SocketIO для використання Eventlet, якщо він доступний, для продакшену
# інакше використовуємо стандартний режим для розробки.
if os.environ.get('FLASK_ENV') == 'production': # Додаємо змінну FLASK_ENV на Heroku пізніше
    socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")
else:
    socketio = SocketIO(app, cors_allowed_origins="*")

online_users = {} 

# --- Моделі Бази Даних ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow) 
    
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy=True))
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref=db.backref('received_messages', lazy=True))

    def __repr__(self):
        return f'<Message from {self.sender.username} to {self.receiver.username}: {self.text}>'

# --- Маршрути Flask ---

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    current_username = session['username']
    
    user = User.query.filter_by(username=current_username).first()
    if not user:
        user = User(username=current_username)
        db.session.add(user)
        db.session.commit()

    all_users = User.query.order_by(User.username).all() 
    
    return render_template(
        'index.html', 
        current_username=current_username,
        all_users=[user.username for user in all_users], 
        online_users=list(online_users.keys()) 
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip() 
        if username:
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Будь ласка, введіть ім'я користувача.")
    return render_template('login.html')

@app.route('/get_private_messages/<recipient_username>', methods=['GET'])
def get_private_messages(recipient_username):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    current_username = session['username']
    
    sender_user = User.query.filter_by(username=current_username).first()
    receiver_user = User.query.filter_by(username=recipient_username).first()

    if not sender_user:
        print(f"ERROR: Current user '{current_username}' not found in DB.")
        return jsonify({'error': 'Current user not found'}), 500
    if not receiver_user:
        print(f"DEBUG: Recipient user '{recipient_username}' not found in DB.")
        return jsonify({'error': 'Recipient user not found'}), 404

    messages = Message.query.filter(
        ((Message.sender_id == sender_user.id) & (Message.receiver_id == receiver_user.id)) |
        ((Message.sender_id == receiver_user.id) & (Message.receiver_id == sender_user.id))
    ).order_by(Message.timestamp).all()

    message_list = []
    for msg in messages:
        message_list.append({
            'username': msg.sender.username, 
            'msg': msg.text,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    print(f"DEBUG: Retrieved {len(message_list)} messages for chat between {current_username} and {recipient_username}.")
    return jsonify(message_list)

# --- Обробники Подій SocketIO ---

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        username = session['username']
        join_room(username) 
        
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username)
            db.session.add(user)
            db.session.commit()

        online_users[username] = request.sid 
        print(f"User {username} connected. SID: {request.sid}")
        emit('update_online_users', list(online_users.keys()), broadcast=True)
    else:
        print("Anonymous user connected.")

@socketio.on('disconnect')
def handle_disconnect():
    disconnected_username = None
    for username, sid in list(online_users.items()): 
        if sid == request.sid:
            disconnected_username = username
            del online_users[username]
            break
    
    if disconnected_username:
        print(f"User {disconnected_username} disconnected. SID: {request.sid}")
        leave_room(disconnected_username) 
        emit('update_online_users', list(online_users.keys()), broadcast=True)
    else:
        print(f"Anonymous user disconnected. SID: {request.sid}")

@socketio.on('send_private_message')
def handle_send_private_message(data):
    if 'username' not in session:
        print("Unauthorized message attempt (no session username).")
        return

    sender_username = session['username']
    recipient_username = data.get('recipient')
    message_text = data.get('msg')

    if not recipient_username or not message_text:
        print("Missing recipient or message text.")
        return

    sender_user = User.query.filter_by(username=sender_username).first()
    receiver_user = User.query.filter_by(username=recipient_username).first()

    if not sender_user:
        print(f"ERROR: Sender user '{sender_username}' not found in DB when sending message.")
        return
    if not receiver_user:
        print(f"ERROR: Receiver user '{recipient_username}' not found in DB when sending message.")
        return

    try:
        new_message = Message(text=message_text, sender_id=sender_user.id, receiver_id=receiver_user.id)
        db.session.add(new_message)
        db.session.commit()
        print(f"Message saved to DB: from {sender_username} to {recipient_username}: '{message_text}'")
    except Exception as e:
        db.session.rollback() 
        print(f"ERROR saving message to DB: {e}")
        return

    message_payload = {
        'sender': sender_username, 
        'recipient': recipient_username, 
        'msg': message_text
    }

    emit('private_message', message_payload, room=sender_username) 
    print(f"Emitted message to sender '{sender_username}' room.")

    if recipient_username in online_users and recipient_username != sender_username:
        emit('private_message', message_payload, room=recipient_username) 
        print(f"Emitted message to recipient '{recipient_username}' room.")
    else:
        print(f"Recipient {recipient_username} is offline or self-messaging. Message saved but not emitted to recipient's room.")

# --- Запуск Сервера ---
if __name__ == '__main__':
    with app.app_context():
        # Створюємо таблиці, якщо вони не існують. 
        # Це буде працювати як для SQLite локально, так і для PostgreSQL на Heroku
        db.create_all() 
    
    # Використовуємо порт, наданий Heroku, або 5000 для локальної розробки
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)