import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text # Імпортуємо text для виконання сирих SQL запитів
import datetime

# --- Налаштування Flask та бази даних ---
app = Flask(__name__)

# КОМАНДА, ЯКУ МИ ЗМІНИЛИ ДЛЯ PostgreSQL
# Використовуємо змінну оточення DATABASE_URL для PostgreSQL на Render.com
# Для локальної розробки (якщо змінна оточення не встановлена) використовуємо SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Рекомендується для Flask-SQLAlchemy

db = SQLAlchemy(app)

# --- Модель даних ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # Додамо поле password для реєстрації/авторизації, якщо воно у вас є
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

# --- Налаштування Flask-SocketIO ---
# Обов'язково вказуємо message_queue для продакшн середовища з Gunicorn/Eventlet
# Для Socket.IO потрібен Redis або інша черга повідомлень для роботи кількох воркерів.
# На Render можна створити Redis інстанс аналогічно PostgreSQL.
# Для початку, якщо ви не плануєте кілька воркерів, можна опустити message_queue,
# але для масштабованості це буде необхідно.
# Якщо у вас є Redis на Render, його URL буде виглядати як redis://...
# socketio = SocketIO(app, message_queue=os.environ.get('REDIS_URL'))
socketio = SocketIO(app) # Починаємо без message_queue для простоти, якщо не було Redis

# Глобальний список для відстеження активних користувачів
# Це дуже простий приклад, в реальному додатку його краще зберігати в базі даних або Redis
online_users = {} # {user_id: socket_id, ...}
user_to_sid = {} # {username: socket_id, ...}
sid_to_user = {} # {socket_id: username, ...}


# --- Маршрути Flask ---

@app.route('/')
def index():
    if 'username' in request.cookies:
        # Якщо користувач авторизований, перенаправляємо на головну сторінку месенджера
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        if not username:
            flash('Ім\'я користувача не може бути порожнім.')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()
        if not user:
            # Якщо користувача немає, створюємо нового
            new_user = User(username=username)
            db.session.add(new_user)
            db.session.commit()
            user = new_user
            flash(f'Нового користувача {username} успішно зареєстровано та авторизовано!', 'success')
        else:
            flash(f'Користувача {username} успішно авторизовано!', 'success')

        response = redirect(url_for('chat'))
        response.set_cookie('username', username)
        return response
    return render_template('login.html')

@app.route('/chat')
def chat():
    username = request.cookies.get('username')
    if not username:
        return redirect(url_for('login'))

    current_user = User.query.filter_by(username=username).first()
    if not current_user:
        # Якщо користувач з cookies не знайдений в БД, змусити його увійти знову
        flash("Користувач не знайдений. Будь ласка, увійдіть знову.")
        response = redirect(url_for('login'))
        response.delete_cookie('username')
        return response

    # Отримуємо всіх користувачів, крім поточного
    all_users = User.query.filter(User.id != current_user.id).all()
    
    # Отримуємо історію повідомлень з останніми 20 повідомленнями, сортованими за часом
    # Це може бути оптимізовано для великих чатів
    messages = Message.query.filter(
        (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
    ).order_by(Message.timestamp.desc()).limit(50).all()
    
    # Перевертаємо порядок, щоб найновіші були знизу
    messages.reverse()

    return render_template('chat.html', username=username, users=all_users, messages=messages)


@app.route('/logout')
def logout():
    response = redirect(url_for('index'))
    response.delete_cookie('username')
    flash('Ви вийшли з системи.', 'info')
    return response

# --- Обробники подій Socket.IO ---

@socketio.on('connect')
def handle_connect():
    username = request.cookies.get('username')
    if username:
        current_user = User.query.filter_by(username=username).first()
        if current_user:
            online_users[current_user.id] = request.sid
            user_to_sid[username] = request.sid
            sid_to_user[request.sid] = username
            join_room(username) # Кожен користувач приєднується до своєї кімнати за іменем
            print(f'User {username} connected. SID: {request.sid}')
            # Повідомити всіх про нового користувача онлайн (можна розширити)
            # emit('user_online', {'username': username}, broadcast=True)
            socketio.emit('update_user_list', get_online_users_list(), broadcast=True)
        else:
            print(f"Error: User {username} from cookie not found in DB on connect. Disconnecting.")
            request.sid.disconnect() # Відключити, якщо користувача немає в БД
    else:
        print("Anonymous user connected (no username in cookies).")
        # Можливо, перенаправити на логін
        # emit('redirect', {'url': url_for('login')})


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in sid_to_user:
        username = sid_to_user[sid]
        current_user = User.query.filter_by(username=username).first()
        if current_user and current_user.id in online_users:
            del online_users[current_user.id]
        if username in user_to_sid:
            del user_to_sid[username]
        del sid_to_user[sid]
        print(f'User {username} disconnected. SID: {sid}')
        # Повідомити всіх, що користувач оффлайн
        # emit('user_offline', {'username': username}, broadcast=True)
        socketio.emit('update_user_list', get_online_users_list(), broadcast=True)
    else:
        print(f'Anonymous SID {sid} disconnected.')


@socketio.on('send_message')
def handle_send_message(data):
    sender_username = data.get('sender')
    receiver_username = data.get('receiver')
    message_text = data.get('message')

    if not sender_username or not receiver_username or not message_text:
        print("Invalid message data received.")
        return

    sender_user = User.query.filter_by(username=sender_username).first()
    receiver_user = User.query.filter_by(username=receiver_username).first()

    if not sender_user:
        print(f"ERROR: Sender user '{sender_username}' not found in DB.")
        return
    if not receiver_user:
        print(f"ERROR: Receiver user '{receiver_username}' not found in DB.")
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
        'recipient': receiver_username,
        'msg': message_text,
        'timestamp': new_message.timestamp.strftime('%H:%M:%S') # Форматуємо час
    }

    # Відправити повідомлення відправнику (у його кімнату)
    emit('private_message', message_payload, room=sender_username)

    # Відправити повідомлення отримувачу (якщо він онлайн і не є відправником)
    if receiver_username in user_to_sid and receiver_username != sender_username:
        emit('private_message', message_payload, room=receiver_username)
        print(f"Emitted message to recipient {receiver_username}'s room.")
    else:
        print(f"Recipient {receiver_username} is offline or self-messaging. Message saved but not emitted to recipient's room.")

# Функція для отримання списку онлайн користувачів
def get_online_users_list():
    online_usernames = [sid_to_user[sid] for sid in sid_to_user.keys()]
    return online_usernames


# --- Запуск Сервера ---
# Цей блок буде виконуватися лише при локальному запуску через `python app.py`.
# На Render Gunicorn запускає додаток.
if __name__ == '__main__':
    with app.app_context():
        # Створюємо таблиці, якщо вони не існують.
        # Для продакшн (Render.com), це краще робити через Shell один раз.
        # Тому тут ми можемо залишити це лише для локальної розробки.
        db.create_all()

    # Використовуємо порт, наданий Render (через змінну середовища PORT), або 5000 для локальної розробки
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)