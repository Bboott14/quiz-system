import sqlalchemy
from flask import session as flask_session
from flask_socketio import emit
from flask_socketio import join_room as socket_join_room
from flask_socketio import leave_room as socket_leave_room

import app.database as database
from app.extensions import socketio
from app.models import GameRoom, Participant, Quiz


@socketio.on('connect')
def handle_connect():
    emit('server_status', {
        'status': 'connected',
        'message': 'Соединение с сервером установлено',
    })


@socketio.on('client_ping')
def handle_client_ping():
    emit('server_pong', {
        'message': 'Socket.IO работает',
    })


@socketio.on('subscribe_room')
def handle_subscribe_room(data):
    user_id = flask_session.get('user_id')

    if user_id is None:
        emit('room_error', {
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        })
        return

    if not isinstance(data, dict):
        emit('room_error', {
            'error': 'invalid_data',
            'message': 'Не передан код комнаты',
        })
        return

    code = str(data.get('code', '')).strip().upper()

    if not code:
        emit('room_error', {
            'error': 'room_code_required',
            'message': 'Укажите код комнаты',
        })
        return

    with database.SessionLocal() as db_session:
        room = db_session.scalar(
            sqlalchemy.select(GameRoom).where(
                GameRoom.code == code
            )
        )

        if room is None:
            emit('room_error', {
                'error': 'room_not_found',
                'message': 'Комната не найдена',
            })
            return

        quiz = db_session.get(Quiz, room.quiz_id)

        participant = db_session.scalar(
            sqlalchemy.select(Participant).where(
                Participant.room_id == room.id,
                Participant.user_id == user_id,
            )
        )

        is_organizer = (
            quiz is not None
            and quiz.organizer_id == user_id
        )

        if participant is None and not is_organizer:
            emit('room_error', {
                'error': 'room_access_denied',
                'message': (
                    'Сначала присоединитесь к комнате'
                ),
            })
            return

        socket_join_room(room.code)

        emit('room_subscribed', {
            'code': room.code,
            'status': room.status,
            'is_organizer': is_organizer,
            'participant_id': (
                participant.id
                if participant is not None
                else None
            ),
        })


@socketio.on('unsubscribe_room')
def handle_unsubscribe_room(data):
    if not isinstance(data, dict):
        return

    code = str(data.get('code', '')).strip().upper()

    if code:
        socket_leave_room(code)

        emit('room_unsubscribed', {
            'code': code,
        })


@socketio.on('disconnect')
def handle_disconnect():
    print('Клиент отключился от Socket.IO')