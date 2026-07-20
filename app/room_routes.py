import secrets
import string
from datetime import datetime, timedelta, timezone

import sqlalchemy
from flask import Blueprint, jsonify, request, session as flask_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

import app.database as database
from app.models import (
    AnswerOption,
    GameRoom,
    Participant,
    Question,
    Quiz,
    User,
)


room_blueprint = Blueprint(
    'rooms',
    __name__,
    url_prefix='/api'
)


ROOM_CODE_LENGTH = 6
ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_room_code():
    return ''.join(
        secrets.choice(ROOM_CODE_ALPHABET)
        for _ in range(ROOM_CODE_LENGTH)
    )


def serialize_participant(participant):
    return {
        'id': participant.id,
        'room_id': participant.room_id,
        'user_id': participant.user_id,
        'nickname': participant.nickname,
        'score': participant.score,
    }


def serialize_room(room, participants=None):
    result = {
        'id': room.id,
        'quiz_id': room.quiz_id,
        'code': room.code,
        'status': room.status,
        'current_question_id': room.current_question_id,
        'started_at': (
            room.started_at.isoformat()
            if room.started_at is not None
            else None
        ),
        'question_started_at': (
            room.question_started_at.isoformat()
            if room.question_started_at is not None
            else None
        ),
        'question_ends_at': (
            room.question_ends_at.isoformat()
            if room.question_ends_at is not None
            else None
        ),
    }

    if participants is not None:
        result['participants'] = [
            serialize_participant(participant)
            for participant in participants
        ]
        result['participant_count'] = len(participants)

    return result


def authentication_error():
    return jsonify({
        'error': 'authentication_required',
        'message': 'Требуется авторизация',
    }), 401


def database_error(message):
    return jsonify({
        'error': 'database_error',
        'message': message,
    }), 500


def get_room_by_code(db_session, code):
    return db_session.scalar(
        sqlalchemy.select(GameRoom).where(
            GameRoom.code == code
        )
    )


def get_room_participants(db_session, room_id):
    statement = (
        sqlalchemy.select(Participant)
        .where(Participant.room_id == room_id)
        .order_by(Participant.id)
    )

    return db_session.scalars(statement).all()


def validate_quiz_readiness(quiz):
    """
    Проверяет, можно ли запускать квиз.

    Возвращает список ошибок. Пустой список означает,
    что квиз готов к запуску.
    """
    errors = []

    questions = sorted(
        quiz.questions,
        key=lambda question: question.position
    )

    if not questions:
        errors.append('В квизе должен быть хотя бы один вопрос')
        return errors

    question_positions = set()

    for question in questions:
        if question.position in question_positions:
            errors.append(
                f'Вопрос {question.id}: позиция повторяется'
            )

        question_positions.add(question.position)

        options = sorted(
            question.answer_options,
            key=lambda option: option.position
        )

        if len(options) < 2:
            errors.append(
                f'Вопрос {question.id}: '
                'должно быть минимум два варианта ответа'
            )
            continue

        correct_count = sum(
            1
            for option in options
            if option.is_correct
        )

        if question.question_type == 'single_choice':
            if correct_count != 1:
                errors.append(
                    f'Вопрос {question.id}: '
                    'для single_choice должен быть '
                    'ровно один правильный вариант'
                )

        elif question.question_type == 'multiple_choice':
            if correct_count < 1:
                errors.append(
                    f'Вопрос {question.id}: '
                    'должен быть хотя бы один '
                    'правильный вариант'
                )

        else:
            errors.append(
                f'Вопрос {question.id}: '
                f'неизвестный тип {question.question_type}'
            )

    return errors


# ---------------------------------------------------------
# Создать игровую комнату
# ---------------------------------------------------------

@room_blueprint.route(
    '/quizzes/<int:quiz_id>/rooms',
    methods=['POST']
)
def create_room(quiz_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    if database.SessionLocal is None:
        return database_error(
            'База данных не инициализирована'
        )

    with database.SessionLocal() as db_session:
        try:
            statement = (
                sqlalchemy.select(Quiz)
                .options(
                    selectinload(Quiz.questions)
                    .selectinload(Question.answer_options)
                )
                .where(
                    Quiz.id == quiz_id,
                    Quiz.organizer_id == user_id,
                )
            )

            quiz = db_session.scalar(statement)

            if quiz is None:
                return jsonify({
                    'error': 'quiz_not_found',
                    'message': 'Квиз не найден',
                }), 404

            readiness_errors = validate_quiz_readiness(quiz)

            if readiness_errors:
                return jsonify({
                    'error': 'quiz_not_ready',
                    'message': 'Квиз не готов к запуску',
                    'details': readiness_errors,
                }), 400

            # Несколько попыток на случай совпадения случайного кода.
            room = None

            for _ in range(10):
                code = generate_room_code()

                existing_room = get_room_by_code(
                    db_session,
                    code
                )

                if existing_room is None:
                    room = GameRoom(
                        quiz=quiz,
                        code=code,
                        status='waiting',
                    )
                    break

            if room is None:
                return jsonify({
                    'error': 'room_code_generation_failed',
                    'message': (
                        'Не удалось сгенерировать код комнаты'
                    ),
                }), 500

            db_session.add(room)
            db_session.commit()
            db_session.refresh(room)

            return jsonify({
                'message': 'Игровая комната создана',
                'room': serialize_room(room, []),
            }), 201

        except IntegrityError:
            db_session.rollback()

            return jsonify({
                'error': 'room_creation_conflict',
                'message': (
                    'Не удалось создать комнату. '
                    'Попробуйте ещё раз'
                ),
            }), 409

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось создать игровую комнату'
            )


# ---------------------------------------------------------
# Получить информацию о комнате
# ---------------------------------------------------------

@room_blueprint.route(
    '/rooms/<string:code>',
    methods=['GET']
)
def get_room(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    code = code.strip().upper()

    with database.SessionLocal() as db_session:
        try:
            room = get_room_by_code(db_session, code)

            if room is None:
                return jsonify({
                    'error': 'room_not_found',
                    'message': 'Комната не найдена',
                }), 404

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

            if not is_organizer and participant is None:
                return jsonify({
                    'error': 'room_access_denied',
                    'message': (
                        'Сначала присоединитесь к комнате'
                    ),
                }), 403

            participants = get_room_participants(
                db_session,
                room.id
            )

            return jsonify({
                'room': serialize_room(
                    room,
                    participants
                ),
                'quiz': {
                    'id': quiz.id,
                    'title': quiz.title,
                    'organizer_id': quiz.organizer_id,
                },
                'is_organizer': is_organizer,
                'current_participant_id': (
                    participant.id
                    if participant is not None
                    else None
                ),
            }), 200

        except SQLAlchemyError:
            return database_error(
                'Не удалось получить комнату'
            )


# ---------------------------------------------------------
# Присоединиться к комнате
# ---------------------------------------------------------

@room_blueprint.route(
    '/rooms/<string:code>/join',
    methods=['POST']
)
def join_room(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True) or {}
    code = code.strip().upper()

    if not isinstance(data, dict):
        return jsonify({
            'error': 'invalid_json',
            'message': (
                'Тело запроса должно быть JSON-объектом'
            ),
        }), 400

    nickname_value = data.get('nickname')

    if nickname_value is not None:
        nickname = str(nickname_value).strip()

        if not nickname:
            return jsonify({
                'error': 'validation_error',
                'fields': {
                    'nickname': 'Никнейм не может быть пустым'
                },
            }), 400

        if len(nickname) > 100:
            return jsonify({
                'error': 'validation_error',
                'fields': {
                    'nickname': (
                        'Никнейм не должен быть '
                        'длиннее 100 символов'
                    )
                },
            }), 400
    else:
        nickname = None

    with database.SessionLocal() as db_session:
        try:
            room = get_room_by_code(db_session, code)

            if room is None:
                return jsonify({
                    'error': 'room_not_found',
                    'message': 'Комната не найдена',
                }), 404

            if room.status != 'waiting':
                return jsonify({
                    'error': 'room_not_waiting',
                    'message': (
                        'Подключение к этой комнате закрыто'
                    ),
                }), 409

            user = db_session.get(User, user_id)

            if user is None:
                flask_session.clear()

                return authentication_error()

            existing_participant = db_session.scalar(
                sqlalchemy.select(Participant).where(
                    Participant.room_id == room.id,
                    Participant.user_id == user_id,
                )
            )

            if existing_participant is not None:
                return jsonify({
                    'error': 'already_joined',
                    'message': (
                        'Вы уже присоединились к комнате'
                    ),
                    'participant': serialize_participant(
                        existing_participant
                    ),
                }), 409

            participant = Participant(
                room=room,
                user=user,
                nickname=nickname or user.name,
                score=0,
            )

            db_session.add(participant)
            db_session.commit()
            db_session.refresh(participant)

            flask_session['participant_id'] = participant.id
            flask_session['room_code'] = room.code

            return jsonify({
                'message': 'Вы присоединились к комнате',
                'participant': serialize_participant(
                    participant
                ),
                'room': serialize_room(room),
            }), 201

        except IntegrityError:
            db_session.rollback()

            return jsonify({
                'error': 'already_joined',
                'message': (
                    'Вы уже присоединились к комнате'
                ),
            }), 409

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось присоединиться к комнате'
            )


# ---------------------------------------------------------
# Запустить игру
# ---------------------------------------------------------

@room_blueprint.route(
    '/rooms/<string:code>/start',
    methods=['POST']
)
def start_room(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    code = code.strip().upper()

    with database.SessionLocal() as db_session:
        try:
            room = get_room_by_code(db_session, code)

            if room is None:
                return jsonify({
                    'error': 'room_not_found',
                    'message': 'Комната не найдена',
                }), 404

            quiz = db_session.scalar(
                sqlalchemy.select(Quiz)
                .options(
                    selectinload(Quiz.questions)
                    .selectinload(Question.answer_options)
                )
                .where(Quiz.id == room.quiz_id)
            )

            if (
                quiz is None
                or quiz.organizer_id != user_id
            ):
                return jsonify({
                    'error': 'room_access_denied',
                    'message': (
                        'Запустить игру может только организатор'
                    ),
                }), 403

            if room.status != 'waiting':
                return jsonify({
                    'error': 'room_already_started',
                    'message': 'Игра уже была запущена',
                }), 409

            readiness_errors = validate_quiz_readiness(quiz)

            if readiness_errors:
                return jsonify({
                    'error': 'quiz_not_ready',
                    'message': 'Квиз не готов к запуску',
                    'details': readiness_errors,
                }), 400

            participants = get_room_participants(
                db_session,
                room.id
            )

            if not participants:
                return jsonify({
                    'error': 'room_has_no_participants',
                    'message': (
                        'Для запуска нужен хотя бы один участник'
                    ),
                }), 409

            questions = sorted(
                quiz.questions,
                key=lambda question: question.position
            )

            first_question = questions[0]

            duration = (
                first_question.time_limit
                or quiz.default_time_limit
                or 30
            )

            now = datetime.now(timezone.utc)

            room.status = 'running'
            room.current_question = first_question
            room.started_at = now
            room.question_started_at = now
            room.question_ends_at = (
                now + timedelta(seconds=duration)
            )

            db_session.commit()
            db_session.refresh(room)

            return jsonify({
                'message': 'Игра запущена',
                'room': serialize_room(
                    room,
                    participants
                ),
                'question': {
                    'id': first_question.id,
                    'text': first_question.text,
                    'question_type': (
                        first_question.question_type
                    ),
                    'time_limit': duration,
                    'points': first_question.points,
                    'position': first_question.position,

                    # Правильность вариантов здесь намеренно
                    # не возвращается.
                    'answer_options': [
                        {
                            'id': option.id,
                            'text': option.text,
                            'position': option.position,
                        }
                        for option in sorted(
                            first_question.answer_options,
                            key=lambda item: item.position
                        )
                    ],
                },
            }), 200

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось запустить игру'
            )