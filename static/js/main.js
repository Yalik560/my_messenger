document.addEventListener('DOMContentLoaded', function() {
    var socket = io(); 

    var messageInput = document.getElementById('messageInput');
    var messagesDiv = document.getElementById('messages');
    var userList = document.getElementById('userList'); 
    var chatHeader = document.getElementById('chatHeader');

    var welcomeScreen = document.getElementById('welcomeScreen'); 
    var privateChatArea = document.getElementById('privateChat'); 

    var currentUsername = document.body.dataset.username; 
    var activeRecipient = null; 

    console.log("DOM Content Loaded.");
    console.log("Current user:", currentUsername);

    // Функція для очищення та завантаження повідомлень для вибраного співрозмовника
    function loadPrivateMessages(recipientUsername) {
        console.log(`Attempting to load private messages for: ${recipientUsername}`);
        messagesDiv.innerHTML = ''; // Очищаємо поточні повідомлення
        chatHeader.textContent = `Чат з ${recipientUsername}`; // Встановлюємо заголовок чату
        activeRecipient = recipientUsername; // Встановлюємо активного співрозмовника

        // Приховуємо вітальний екран та показуємо панель чату
        welcomeScreen.classList.remove('active');
        privateChatArea.classList.add('active'); 

        // Завантажуємо історію повідомлень з сервера
        fetch(`/get_private_messages/${recipientUsername}`)
            .then(response => {
                console.log(`Fetch response status for ${recipientUsername}: ${response.status}`);
                if (!response.ok) {
                    // Якщо є помилка, виводимо її і відображаємо користувачу
                    console.error('Failed to load private messages:', response.statusText);
                    // Додатково можна відобразити повідомлення про помилку користувачу
                    messagesDiv.innerHTML = `<p style="color: red; text-align: center;">Помилка завантаження повідомлень: ${response.statusText}</p>`;
                    throw new Error('Network response was not ok ' + response.statusText);
                }
                return response.json();
            })
            .then(messages => {
                console.log(`Received historical messages for ${recipientUsername}:`, messages);
                if (messages.length === 0) {
                    messagesDiv.innerHTML = `<p style="text-align: center; color: #888;">Повідомлень ще немає. Почніть чат!</p>`;
                } else {
                    messages.forEach(msg => {
                        appendMessage(msg.username, msg.msg);
                    });
                }
                messagesDiv.scrollTop = messagesDiv.scrollHeight; // Прокрутка до низу
            })
            .catch(error => console.error('Error loading private messages:', error));
    }

    // Допоміжна функція для додавання повідомлення в DOM
    function appendMessage(sender, msg) {
        console.log(`Appending message: Sender=${sender}, Message='${msg}'`);
        var p = document.createElement('p');
        p.innerHTML = '<b>' + sender + ':</b> ' + msg;
        
        // Визначаємо, хто відправник, щоб додати відповідний клас
        if (sender === currentUsername) {
            p.classList.add('my-message'); 
        } else {
            p.classList.add('other-message'); 
        }

        messagesDiv.appendChild(p);
        messagesDiv.scrollTop = messagesDiv.scrollHeight; // Автоматична прокрутка при додаванні нового повідомлення
        console.log("Message appended to messagesDiv:", p);
    }

    // --- Обробники подій SocketIO ---

    // Обробник події 'private_message' від сервера
    socket.on('private_message', function(data) {
        console.log(`Received private_message: Sender=${data.sender}, Recipient=${data.recipient}, Msg='${data.msg}'`);
        console.log(`Current activeRecipient=${activeRecipient}, currentUsername=${currentUsername}`);

        // Додаємо повідомлення лише якщо воно стосується поточного активного чату
        // (тобто або ми відправили комусь, або ми отримали від когось, і цей чат відкритий)
        if ((data.sender === activeRecipient && data.recipient === currentUsername) || 
            (data.sender === currentUsername && data.recipient === activeRecipient)) {
            appendMessage(data.sender, data.msg);
        } else if (data.recipient === currentUsername) {
            // Якщо повідомлення прийшло нам, але чат з цим користувачем неактивний,
            // можна додати візуальне сповіщення (наприклад, підсвітити ім'я в userList).
            console.log(`New message from ${data.sender}, but chat not active. Highlighting user.`);
            var senderLi = userList.querySelector(`li[data-username="${data.sender}"]`);
            if (senderLi && !senderLi.classList.contains('active')) {
                senderLi.classList.add('has-new-message'); 
            }
        }
    });

    // Обробник події 'update_online_users' від сервера
    socket.on('update_online_users', function(onlineUsers) {
        console.log("Online users updated:", onlineUsers);
        // Оновлюємо статус онлайн/офлайн для кожного користувача у списку
        Array.from(userList.children).forEach(function(li) {
            var username = li.dataset.username;
            if (onlineUsers.includes(username)) {
                li.classList.add('online');
                li.classList.remove('offline');
            } else {
                li.classList.add('offline');
                li.classList.remove('online');
            }
        });
    });

    // --- Функції інтерфейсу ---

    // Функція для надсилання приватного повідомлення на сервер
    window.sendMessage = function() {
        var msg = messageInput.value;
        if (msg.trim() !== '' && activeRecipient) { 
            console.log(`Sending message to ${activeRecipient}: '${msg}'`);
            // Надсилаємо повідомлення на сервер
            socket.emit('send_private_message', { msg: msg, recipient: activeRecipient }); 
            messageInput.value = ''; 
        } else {
            console.log("Message not sent: input empty or no recipient selected.");
        }
    };

    // Обробка кліків на іменах користувачів у списку
    userList.addEventListener('click', function(event) {
        var targetLi = event.target.closest('li[data-username]'); 
        if (targetLi) {
            console.log(`User clicked: ${targetLi.dataset.username}`);
            // Знімаємо клас 'active' з попередньо вибраного елемента
            var currentActive = userList.querySelector('li.active');
            if (currentActive) {
                currentActive.classList.remove('active');
            }
            
            // Додаємо клас 'active' до нового вибраного елемента
            targetLi.classList.add('active');
            // Прибираємо можливий клас "нового повідомлення" при відкритті чату
            targetLi.classList.remove('has-new-message'); 
            
            // Завантажуємо повідомлення для вибраного користувача
            loadPrivateMessages(targetLi.dataset.username);

            if (messageInput) {
                messageInput.focus();
            }
        }
    });

    // Надсилання повідомлення при натисканні клавіші Enter у полі вводу
    if (messageInput) { 
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    }

    // Ініціалізація: показуємо вітальний екран при першому завантаженні
    welcomeScreen.classList.add('active');
    privateChatArea.classList.remove('active');
    console.log("Initial state: Welcome screen active, Private chat area inactive.");
});