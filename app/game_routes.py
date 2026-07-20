from datetime import datetime, timedelta, timezone

import sqlalchemy
from flask import Blueprint, jsonify, request, session as flask_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

import app.database as database
from app.extensions import socketio
from app.models import (
    AnswerOption,
    GameRoom,
    Participant,
    ParticipantAnswer,
    Question,
    Quiz,
    SelectedOption,
)


game_blueprint = Blueprint(
    'game',
    __name__,
    url_prefix='/api'
)


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


def as_utc(value):
    """
    SQLite иногда возвращает DateTime без timezone,
    даже если колонка объявлена timezone=True.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_room(db_session, code):
    return db_session.scalar(
        sqlalchemy.select(GameRoom).where(
            GameRoom.code == code
        )
    )


def get_participant(db_session, room_id, user_id):
    return db_session.scalar(
        sqlalchemy.select(Participant).where(
            Participant.room_id == room_id,
            Participant.user_id == user_id,
        )
    )


def serialize_public_question(question, room):
    options = sorted(
        question.answer_options,
        key=lambda option: option.position
    )

    started_at = as_utc(room.question_started_at)
    ends_at = as_utc(room.question_ends_at)

    duration = None

    if started_at is not None and ends_at is not None:
        duration = max(
            1,
            int((ends_at - started_at).total_seconds())
        )

    return {
        'id': question.id,
        'text': question.text,
        'image_path': question.image_path,
        'question_type': question.question_type,
        'points': question.points,
        'position': question.position,
        'time_limit': duration,
        'started_at': (
            started_at.isoformat()
            if started_at is not None
            else None
        ),
        'ends_at': (
            ends_at.isoformat()
            if ends_at is not None
            else None
        ),
        'answer_options': [
            {
                'id': option.id,
                'text': option.text,
                'position': option.position,
            }
            for option in options
        ],
    }


def build_leaderboard(participants):
    ordered = sorted(
        participants,
        key=lambda participant: (
            -participant.score,
            participant.joined_at,
            participant.id,
        )
    )

    return [
        {
            'rank': index,
            'participant_id': participant.id,
            'nickname': participant.nickname,
            'score': participant.score,
        }
        for index, participant in enumerate(
            ordered,
            start=1
        )
    ]


# ---------------------------------------------------------
# Отправить ответ
# ---------------------------------------------------------

@game_blueprint.route(
    '/rooms/<string:code>/answers',
    methods=['POST']
)
def submit_answer(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            'error': 'invalid_json',
            'message': (
                'Тело запроса должно быть JSON-объектом'
            ),
        }), 400

    option_ids = data.get('option_ids')

    if not isinstance(option_ids, list):
        return jsonify({
            'error': 'validation_error',
            'fields': {
                'option_ids': (
                    'Поле option_ids должно быть массивом'
                )
            },
        }), 400

    normalized_ids = []

    for value in option_ids:
        if isinstance(value, bool):
            return jsonify({
                'error': 'validation_error',
                'fields': {
                    'option_ids': (
                        'ID вариантов должны быть целыми числами'
                    )
                },
            }), 400

        try:
            option_id = int(value)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'validation_error',
                'fields': {
                    'option_ids': (
                        'ID вариантов должны быть целыми числами'
                    )
                },
            }), 400

        if option_id <= 0:
            return jsonify({
                'error': 'validation_error',
                'fields': {
                    'option_ids': (
                        'ID вариантов должны быть положительными'
                    )
                },
            }), 400

        normalized_ids.append(option_id)

    # Убираем дубликаты с сохранением порядка.
    normalized_ids = list(dict.fromkeys(normalized_ids))

    if not normalized_ids:
        return jsonify({
            'error': 'validation_error',
            'fields': {
                'option_ids': (
                    'Выберите хотя бы один вариант ответа'
                )
            },
        }), 400

    code = code.strip().upper()

    with database.SessionLocal() as db_session:
        try:
            room = db_session.scalar(
                sqlalchemy.select(GameRoom)
                .options(
                    selectinload(GameRoom.current_question)
                    .selectinload(Question.answer_options)
                )
                .where(GameRoom.code == code)
            )

            if room is None:
                return jsonify({
                    'error': 'room_not_found',
                    'message': 'Комната не найдена',
                }), 404

            if room.status != 'running':
                return jsonify({
                    'error': 'game_not_running',
                    'message': 'Игра сейчас не запущена',
                }), 409

            if room.current_question is None:
                return jsonify({
                    'error': 'current_question_missing',
                    'message': 'Текущий вопрос не установлен',
                }), 409

            participant = get_participant(
                db_session,
                room.id,
                user_id
            )

            if participant is None:
                return jsonify({
                    'error': 'participant_not_found',
                    'message': (
                        'Вы не являетесь участником комнаты'
                    ),
                }), 403

            question = room.current_question

            existing_answer = db_session.scalar(
                sqlalchemy.select(ParticipantAnswer).where(
                    ParticipantAnswer.participant_id
                    == participant.id,
                    ParticipantAnswer.question_id
                    == question.id,
                )
            )

            if existing_answer is not None:
                return jsonify({
                    'error': 'answer_already_submitted',
                    'message': (
                        'Ответ на этот вопрос уже отправлен'
                    ),
                }), 409

            now = datetime.now(timezone.utc)
            question_started_at = as_utc(
                room.question_started_at
            )
            question_ends_at = as_utc(
                room.question_ends_at
            )

            if question_started_at is None:
                return jsonify({
                    'error': 'question_not_started',
                    'message': 'Вопрос ещё не был запущен',
                }), 409

            if (
                question_ends_at is not None
                and now > question_ends_at
            ):
                return jsonify({
                    'error': 'answer_time_expired',
                    'message': (
                        'Время для ответа закончилось'
                    ),
                }), 409

            if (
                question.question_type == 'single_choice'
                and len(normalized_ids) != 1
            ):
                return jsonify({
                    'error': 'validation_error',
                    'fields': {
                        'option_ids': (
                            'Для single_choice необходимо '
                            'выбрать ровно один вариант'
                        )
                    },
                }), 400

            selected_options = db_session.scalars(
                sqlalchemy.select(AnswerOption).where(
                    AnswerOption.question_id == question.id,
                    AnswerOption.id.in_(normalized_ids),
                )
            ).all()

            if len(selected_options) != len(normalized_ids):
                return jsonify({
                    'error': 'invalid_answer_options',
                    'message': (
                        'Один или несколько вариантов '
                        'не принадлежат текущему вопросу'
                    ),
                }), 400

            correct_ids = {
                option.id
                for option in question.answer_options
                if option.is_correct
            }

            selected_ids = {
                option.id
                for option in selected_options
            }

            is_correct = selected_ids == correct_ids

            response_time_ms = max(
                0,
                int(
                    (
                        now - question_started_at
                    ).total_seconds() * 1000
                )
            )

            awarded_points = 0

            if is_correct:
                if question_ends_at is None:
                    awarded_points = question.points
                else:
                    total_ms = max(
                        1,
                        int(
                            (
                                question_ends_at
                                - question_started_at
                            ).total_seconds() * 1000
                        )
                    )

                    remaining_ratio = max(
                        0.0,
                        min(
                            1.0,
                            1.0 - response_time_ms / total_ms
                        )
                    )

                    # За правильность выдаётся минимум 50%.
                    # Остальные 50% зависят от скорости.
                    multiplier = 0.5 + 0.5 * remaining_ratio

                    awarded_points = int(
                        round(question.points * multiplier)
                    )

            answer = ParticipantAnswer(
                participant=participant,
                question=question,
                submitted_at=now,
                response_time_ms=response_time_ms,
                is_correct=is_correct,
                awarded_points=awarded_points,
            )

            for option in selected_options:
                answer.selected_options.append(
                    SelectedOption(answer_option=option)
                )

            participant.score += awarded_points

            db_session.add(answer)
            db_session.commit()
            db_session.refresh(answer)

            answer_count = db_session.scalar(
                sqlalchemy.select(
                    sqlalchemy.func.count(
                        ParticipantAnswer.id
                    )
                ).where(
                    ParticipantAnswer.question_id
                    == question.id,
                    ParticipantAnswer.participant_id.in_(
                        sqlalchemy.select(Participant.id).where(
                            Participant.room_id == room.id
                        )
                    ),
                )
            )

            participant_count = db_session.scalar(
                sqlalchemy.select(
                    sqlalchemy.func.count(Participant.id)
                ).where(
                    Participant.room_id == room.id
                )
            )

            socketio.emit(
                'answer_received',
                {
                    'participant_id': participant.id,
                    'question_id': question.id,
                    'answer_count': answer_count,
                    'participant_count': participant_count,
                },
                to=room.code
            )

            return jsonify({
                'message': 'Ответ принят',
                'answer': {
                    'id': answer.id,
                    'question_id': question.id,
                    'selected_option_ids': normalized_ids,
                    'is_correct': is_correct,
                    'response_time_ms': response_time_ms,
                    'awarded_points': awarded_points,
                },
                'participant': {
                    'id': participant.id,
                    'nickname': participant.nickname,
                    'score': participant.score,
                },
            }), 201

        except IntegrityError:
            db_session.rollback()

            return jsonify({
                'error': 'answer_already_submitted',
                'message': (
                    'Ответ на этот вопрос уже был отправлен'
                ),
            }), 409

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось сохранить ответ'
            )


# ---------------------------------------------------------
# Перейти к следующему вопросу
# ---------------------------------------------------------

@game_blueprint.route(
    '/rooms/<string:code>/next',
    methods=['POST']
)
def next_question(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    code = code.strip().upper()

    with database.SessionLocal() as db_session:
        try:
            room = get_room(db_session, code)

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
                        'Переключать вопросы может '
                        'только организатор'
                    ),
                }), 403

            if room.status != 'running':
                return jsonify({
                    'error': 'game_not_running',
                    'message': 'Игра сейчас не запущена',
                }), 409

            questions = sorted(
                quiz.questions,
                key=lambda question: question.position
            )

            if not questions:
                return jsonify({
                    'error': 'quiz_has_no_questions',
                    'message': 'В квизе нет вопросов',
                }), 409

            current_index = next(
                (
                    index
                    for index, question in enumerate(questions)
                    if question.id == room.current_question_id
                ),
                None
            )

            if current_index is None:
                return jsonify({
                    'error': 'current_question_missing',
                    'message': (
                        'Текущий вопрос не найден в квизе'
                    ),
                }), 409

            previous_question = questions[current_index]

            correct_option_ids = [
                option.id
                for option in previous_question.answer_options
                if option.is_correct
            ]

            answers = db_session.scalars(
                sqlalchemy.select(ParticipantAnswer)
                .join(
                    Participant,
                    ParticipantAnswer.participant_id
                    == Participant.id
                )
                .where(
                    Participant.room_id == room.id,
                    ParticipantAnswer.question_id
                    == previous_question.id,
                )
            ).all()

            previous_result = {
                'question_id': previous_question.id,
                'correct_option_ids': correct_option_ids,
                'answer_count': len(answers),
                'correct_answer_count': sum(
                    1 for answer in answers
                    if answer.is_correct
                ),
            }

            participants = db_session.scalars(
                sqlalchemy.select(Participant)
                .where(Participant.room_id == room.id)
            ).all()

            leaderboard = build_leaderboard(participants)

            # Последний вопрос — завершаем игру.
            if current_index + 1 >= len(questions):
                now = datetime.now(timezone.utc)

                room.status = 'finished'
                room.finished_at = now
                room.current_question = None
                room.question_started_at = None
                room.question_ends_at = None

                db_session.commit()

                payload = {
                    'room_code': room.code,
                    'status': 'finished',
                    'previous_result': previous_result,
                    'leaderboard': leaderboard,
                }

                socketio.emit(
                    'game_finished',
                    payload,
                    to=room.code
                )

                return jsonify({
                    'message': 'Игра завершена',
                    **payload,
                }), 200

            next_item = questions[current_index + 1]

            duration = (
                next_item.time_limit
                or quiz.default_time_limit
                or 30
            )

            now = datetime.now(timezone.utc)

            room.current_question = next_item
            room.question_started_at = now
            room.question_ends_at = (
                now + timedelta(seconds=duration)
            )

            db_session.commit()

            question_payload = serialize_public_question(
                next_item,
                room
            )

            socketio.emit(
                'question_finished',
                {
                    'room_code': room.code,
                    'result': previous_result,
                    'leaderboard': leaderboard,
                },
                to=room.code
            )

            socketio.emit(
                'question_started',
                {
                    'room_code': room.code,
                    'question': question_payload,
                },
                to=room.code
            )

            return jsonify({
                'message': 'Следующий вопрос запущен',
                'previous_result': previous_result,
                'leaderboard': leaderboard,
                'question': question_payload,
            }), 200

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось переключить вопрос'
            )


# ---------------------------------------------------------
# Итоговая таблица
# ---------------------------------------------------------

@game_blueprint.route(
    '/rooms/<string:code>/results',
    methods=['GET']
)
def get_results(code):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    code = code.strip().upper()

    with database.SessionLocal() as db_session:
        try:
            room = get_room(db_session, code)

            if room is None:
                return jsonify({
                    'error': 'room_not_found',
                    'message': 'Комната не найдена',
                }), 404

            quiz = db_session.get(Quiz, room.quiz_id)

            participant = get_participant(
                db_session,
                room.id,
                user_id
            )

            is_organizer = (
                quiz is not None
                and quiz.organizer_id == user_id
            )

            if not is_organizer and participant is None:
                return jsonify({
                    'error': 'room_access_denied',
                    'message': 'Нет доступа к результатам',
                }), 403

            if room.status != 'finished':
                return jsonify({
                    'error': 'game_not_finished',
                    'message': 'Игра ещё не завершена',
                }), 409

            participants = db_session.scalars(
                sqlalchemy.select(Participant)
                .where(Participant.room_id == room.id)
            ).all()

            return jsonify({
                'room': {
                    'id': room.id,
                    'code': room.code,
                    'status': room.status,
                    'finished_at': (
                        as_utc(room.finished_at).isoformat()
                        if room.finished_at is not None
                        else None
                    ),
                },
                'quiz': {
                    'id': quiz.id,
                    'title': quiz.title,
                },
                'leaderboard': build_leaderboard(
                    participants
                ),
            }), 200

        except SQLAlchemyError:
            return database_error(
                'Не удалось получить результаты'
            )