import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text # Можливо, не використовується, але залишаю, якщо було у вашому коді
import datetime

# --- Налаштування Flask та бази даних ---
app = Flask(__name__)

# Використання змінної середовища DATABASE_URL для PostgreSQL,
# або відкат до SQLite для локальної розробки, якщо змінна не встановлена.
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


# --- Модель даних ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # password = db.Column(db.String(120), nullable=False) # Якщо ви не використовуєте паролі, залиште закоментованим або видаліть

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

# --- Налаштування Flask-SocketIO ---
socketio = SocketIO(app)

online_users = {}
user_to_sid = {}
sid_to_user = {}


# --- Маршрути Flask ---
@app.route('/')
def index():
    if 'username' in request.cookies:
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']

        user = User.query.filter_by(username=username).first()

        if user:
            # Якщо користувач існує, просто входимо
            response = make_response(redirect(url_for('chat')))
            response.set_cookie('username', username)
            flash('Успішний вхід!', 'success')
            return response
        else:
            # Якщо користувача немає, реєструємо його
            try:
                new_user = User(username=username)
                db.session.add(new_user)
                db.session.commit()
                response = make_response(redirect(url_for('chat')))
                response.set_cookie('username', username)
                flash('Ви успішно зареєстровані та увійшли!', 'success')
                return response
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при реєстрації: {e}', 'error')
                # Якщо помилка реєстрації, повертаємося на сторінку логіну
                return render_template('login.html')
    # Для GET-запитів, просто відображаємо сторінку входу
    return render_template('login.html')

@app.route('/chat')
def chat():
    if 'username' not in request.cookies:
        return redirect(url_for('index'))
    current_username = request.cookies.get('username')
    
    # Отримати всіх користувачів, крім поточного
    all_users = User.query.filter(User.username != current_username).all()
    
    return render_template('chat.html', current_username=current_username, users=all_users)


@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('index')))
    response.set_cookie('username', '', expires=0) # Видаляємо куки
    flash('Ви вийшли з системи.', 'info')
    return response

# --- Обробники подій Socket.IO ---
@socketio.on('connect')
def handle_connect():
    username = request.cookies.get('username')
    if username:
        online_users[username] = request.sid
        user_to_sid[username] = request.sid
        sid_to_user[request.sid] = username
        emit('user_list_update', get_online_users_list(), broadcast=True)
        print(f'{username} connected. Online users: {online_users.keys()}')
    else:
        print("Unauthenticated user connected.")

@socketio.on('disconnect')
def handle_disconnect():
    username = sid_to_user.get(request.sid)
    if username and username in online_users:
        del online_users[username]
        del user_to_sid[username]
        del sid_to_user[request.sid]
        emit('user_list_update', get_online_users_list(), broadcast=True)
        print(f'{username} disconnected. Online users: {online_users.keys()}')

@socketio.on('send_message')
def handle_send_message(data):
    sender_username = data.get('sender')
    receiver_username = data.get('receiver')
    message_text = data.get('message')

    sender_user = User.query.filter_by(username=sender_username).first()
    receiver_user = User.query.filter_by(username=receiver_username).first()

    if not sender_user:
        print(f"ERROR: Sender user '{sender_username}' not found in DB when sending message.")
        return
    if not receiver_user:
        print(f"ERROR: Receiver user '[{receiver_username}]' not found in DB when sending message.")
        return

    try:
        new_message = Message(
            sender_id=sender_user.id,
            receiver_id=receiver_user.id,
            message_text=message_text
        )
        db.session.add(new_message)
        db.session.commit()
        print(f"Message saved to DB: from {sender_username} to {receiver_username}: {message_text}")
    except Exception as e:
        db.session.rollback()
        print(f"ERROR saving message to DB: {e}")
        return

    message_payload = {
        'sender': sender_username,
        'receiver': receiver_username,
        'msg': message_text
    }

    # Відправити повідомлення відправнику (щоб він бачив його у своєму чаті)
    emit('private_message', message_payload, room=online_users.get(sender_username))

    # Відправити повідомлення отримувачу, якщо він онлайн
    if receiver_username in online_users and receiver_username != sender_username:
        emit('private_message', message_payload, room=online_users.get(receiver_username))
    else:
        print(f"Recipient {receiver_username} is offline or self-messaging. Message saved but not emitted to recipient's room.")


def get_online_users_list():
    return list(online_users.keys())

# --- Запуск Сервера ---
if __name__ == '__main__':
    # db.create_all()  # Цей рядок ПЕРЕНЕСЕНО вище у ТИМЧАСОВИЙ БЛОК для Render.com

    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)