from flask_socketio import emit

from app.extensions import socketio


@socketio.on('connect')
def handle_connect():
    emit('server_status', {
        'status': 'connected',
        'message': 'Соединение с сервером установлено'
    })


@socketio.on('client_ping')
def handle_client_ping():
    emit('server_pong', {
        'message': 'Socket.IO работает'
    })


@socketio.on('disconnect')
def handle_disconnect():
    print('Клиент отключился от Socket.IO')