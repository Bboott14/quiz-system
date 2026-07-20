import sqlalchemy
from flask import Blueprint, jsonify, request, session as flask_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

import app.database as database
from app.models import AnswerOption, Question, Quiz, User


quiz_blueprint = Blueprint(
    'quizzes',
    __name__,
    url_prefix='/api/quizzes'
)


ALLOWED_QUIZ_STATUSES = {
    'draft',
    'ready',
    'archived',
}

ALLOWED_QUESTION_TYPES = {
    'single_choice',
    'multiple_choice',
}


def serialize_answer_option(option):
    return {
        'id': option.id,
        'text': option.text,
        'is_correct': option.is_correct,
        'position': option.position,
    }


def serialize_question(question):
    options = sorted(
        question.answer_options,
        key=lambda item: item.position
    )

    return {
        'id': question.id,
        'text': question.text,
        'image_path': question.image_path,
        'question_type': question.question_type,
        'time_limit': question.time_limit,
        'points': question.points,
        'position': question.position,
        'answer_options': [
            serialize_answer_option(option)
            for option in options
        ],
    }


def serialize_quiz(quiz, include_questions=False):
    result = {
        'id': quiz.id,
        'organizer_id': quiz.organizer_id,
        'title': quiz.title,
        'description': quiz.description,
        'default_time_limit': quiz.default_time_limit,
        'status': quiz.status,
        'created_at': (
            quiz.created_at.isoformat()
            if quiz.created_at is not None
            else None
        ),
        'updated_at': (
            quiz.updated_at.isoformat()
            if quiz.updated_at is not None
            else None
        ),
    }

    if include_questions:
        questions = sorted(
            quiz.questions,
            key=lambda item: item.position
        )

        result['questions'] = [
            serialize_question(question)
            for question in questions
        ]

    return result


def get_authenticated_user_id():
    return flask_session.get('user_id')


def validate_quiz_data(data, partial=False):
    errors = {}

    if not isinstance(data, dict):
        return {
            'body': 'Тело запроса должно быть JSON-объектом'
        }

    if not partial or 'title' in data:
        title = str(data.get('title', '')).strip()

        if not title:
            errors['title'] = 'Укажите название квиза'
        elif len(title) > 200:
            errors['title'] = (
                'Название не должно быть длиннее 200 символов'
            )

    if 'description' in data:
        description = data.get('description')

        if (
            description is not None
            and not isinstance(description, str)
        ):
            errors['description'] = (
                'Описание должно быть строкой или null'
            )

    if not partial or 'default_time_limit' in data:
        time_limit = data.get('default_time_limit', 30)

        if isinstance(time_limit, bool):
            errors['default_time_limit'] = (
                'Время должно быть целым числом'
            )
        else:
            try:
                time_limit = int(time_limit)

                if time_limit <= 0:
                    errors['default_time_limit'] = (
                        'Время должно быть больше нуля'
                    )
            except (TypeError, ValueError):
                errors['default_time_limit'] = (
                    'Время должно быть целым числом'
                )

    if 'status' in data:
        status = data.get('status')

        if status not in ALLOWED_QUIZ_STATUSES:
            errors['status'] = (
                'Допустимые статусы: draft, ready, archived'
            )

    return errors


def validate_questions(questions):
    errors = []

    if questions is None:
        return errors

    if not isinstance(questions, list):
        return ['Поле questions должно быть массивом']

    positions = set()

    for question_index, question_data in enumerate(questions):
        prefix = f'questions[{question_index}]'

        if not isinstance(question_data, dict):
            errors.append(f'{prefix}: ожидается объект')
            continue

        text = str(question_data.get('text', '')).strip()

        if not text:
            errors.append(f'{prefix}.text: укажите текст вопроса')

        question_type = question_data.get(
            'question_type',
            'single_choice'
        )

        if question_type not in ALLOWED_QUESTION_TYPES:
            errors.append(
                f'{prefix}.question_type: некорректный тип'
            )

        position = question_data.get(
            'position',
            question_index + 1
        )

        try:
            position = int(position)

            if position <= 0:
                raise ValueError

            if position in positions:
                errors.append(
                    f'{prefix}.position: позиция повторяется'
                )

            positions.add(position)

        except (TypeError, ValueError):
            errors.append(
                f'{prefix}.position: должно быть положительным числом'
            )

        options = question_data.get('answer_options', [])

        if not isinstance(options, list):
            errors.append(
                f'{prefix}.answer_options: ожидается массив'
            )
            continue

        option_positions = set()

        for option_index, option_data in enumerate(options):
            option_prefix = (
                f'{prefix}.answer_options[{option_index}]'
            )

            if not isinstance(option_data, dict):
                errors.append(
                    f'{option_prefix}: ожидается объект'
                )
                continue

            option_text = str(
                option_data.get('text', '')
            ).strip()

            if not option_text:
                errors.append(
                    f'{option_prefix}.text: укажите вариант ответа'
                )

            option_position = option_data.get(
                'position',
                option_index + 1
            )

            try:
                option_position = int(option_position)

                if option_position <= 0:
                    raise ValueError

                if option_position in option_positions:
                    errors.append(
                        f'{option_prefix}.position: '
                        'позиция повторяется'
                    )

                option_positions.add(option_position)

            except (TypeError, ValueError):
                errors.append(
                    f'{option_prefix}.position: '
                    'должно быть положительным числом'
                )

    return errors


# ---------------------------------------------------------
# Создать квиз
# ---------------------------------------------------------

@quiz_blueprint.route('', methods=['POST'])
def create_quiz():
    user_id = get_authenticated_user_id()

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        }), 401

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    errors = validate_quiz_data(data)
    question_errors = validate_questions(
        data.get('questions')
    )

    if question_errors:
        errors['questions'] = question_errors

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    if database.SessionLocal is None:
        return jsonify({
            'error': 'database_not_initialized',
        }), 500

    with database.SessionLocal() as db_session:
        try:
            user = db_session.get(User, user_id)

            if user is None:
                flask_session.clear()

                return jsonify({
                    'error': 'authentication_required',
                    'message': 'Пользователь не найден',
                }), 401

            quiz = Quiz(
                organizer=user,
                title=str(data['title']).strip(),
                description=data.get('description'),
                default_time_limit=int(
                    data.get('default_time_limit', 30)
                ),
                status=data.get('status', 'draft'),
            )

            for question_index, question_data in enumerate(
                data.get('questions', [])
            ):
                question = Question(
                    quiz=quiz,
                    text=str(question_data['text']).strip(),
                    image_path=question_data.get('image_path'),
                    question_type=question_data.get(
                        'question_type',
                        'single_choice'
                    ),
                    time_limit=question_data.get('time_limit'),
                    points=int(question_data.get('points', 100)),
                    position=int(
                        question_data.get(
                            'position',
                            question_index + 1
                        )
                    ),
                )

                for option_index, option_data in enumerate(
                    question_data.get('answer_options', [])
                ):
                    AnswerOption(
                        question=question,
                        text=str(option_data['text']).strip(),
                        is_correct=bool(
                            option_data.get('is_correct', False)
                        ),
                        position=int(
                            option_data.get(
                                'position',
                                option_index + 1
                            )
                        ),
                    )

            db_session.add(quiz)
            db_session.commit()

            quiz_id = quiz.id

            statement = (
                sqlalchemy.select(Quiz)
                .options(
                    selectinload(Quiz.questions)
                    .selectinload(Question.answer_options)
                )
                .where(Quiz.id == quiz_id)
            )

            quiz = db_session.scalar(statement)

            return jsonify({
                'message': 'Квиз создан',
                'quiz': serialize_quiz(
                    quiz,
                    include_questions=True
                ),
            }), 201

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_quiz_data',
                'message': 'Некорректные данные квиза',
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось создать квиз',
            }), 500


# ---------------------------------------------------------
# Получить список своих квизов
# ---------------------------------------------------------

@quiz_blueprint.route('', methods=['GET'])
def get_quizzes():
    user_id = get_authenticated_user_id()

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        }), 401

    with database.SessionLocal() as db_session:
        try:
            statement = (
                sqlalchemy.select(Quiz)
                .where(Quiz.organizer_id == user_id)
                .order_by(Quiz.created_at.desc())
            )

            quizzes = db_session.scalars(statement).all()

            return jsonify({
                'quizzes': [
                    serialize_quiz(quiz)
                    for quiz in quizzes
                ],
                'count': len(quizzes),
            }), 200

        except SQLAlchemyError:
            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось получить квизы',
            }), 500


# ---------------------------------------------------------
# Получить один квиз
# ---------------------------------------------------------

@quiz_blueprint.route('/<int:quiz_id>', methods=['GET'])
def get_quiz(quiz_id):
    user_id = get_authenticated_user_id()

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        }), 401

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

            return jsonify({
                'quiz': serialize_quiz(
                    quiz,
                    include_questions=True
                ),
            }), 200

        except SQLAlchemyError:
            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось получить квиз',
            }), 500


# ---------------------------------------------------------
# Изменить основные поля квиза
# ---------------------------------------------------------

@quiz_blueprint.route('/<int:quiz_id>', methods=['PATCH'])
def update_quiz(quiz_id):
    user_id = get_authenticated_user_id()

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        }), 401

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    allowed_fields = {
        'title',
        'description',
        'default_time_limit',
        'status',
    }

    unknown_fields = set(data) - allowed_fields

    if unknown_fields:
        return jsonify({
            'error': 'unknown_fields',
            'fields': sorted(unknown_fields),
        }), 400

    if not data:
        return jsonify({
            'error': 'empty_request',
            'message': 'Не переданы поля для изменения',
        }), 400

    errors = validate_quiz_data(data, partial=True)

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    with database.SessionLocal() as db_session:
        try:
            quiz = db_session.scalar(
                sqlalchemy.select(Quiz).where(
                    Quiz.id == quiz_id,
                    Quiz.organizer_id == user_id,
                )
            )

            if quiz is None:
                return jsonify({
                    'error': 'quiz_not_found',
                    'message': 'Квиз не найден',
                }), 404

            if 'title' in data:
                quiz.title = str(data['title']).strip()

            if 'description' in data:
                quiz.description = data['description']

            if 'default_time_limit' in data:
                quiz.default_time_limit = int(
                    data['default_time_limit']
                )

            if 'status' in data:
                quiz.status = data['status']

            db_session.commit()
            db_session.refresh(quiz)

            return jsonify({
                'message': 'Квиз обновлён',
                'quiz': serialize_quiz(quiz),
            }), 200

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_quiz_data',
                'message': 'Некорректные данные квиза',
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось обновить квиз',
            }), 500


# ---------------------------------------------------------
# Удалить квиз
# ---------------------------------------------------------

@quiz_blueprint.route('/<int:quiz_id>', methods=['DELETE'])
def delete_quiz(quiz_id):
    user_id = get_authenticated_user_id()

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация',
        }), 401

    with database.SessionLocal() as db_session:
        try:
            quiz = db_session.scalar(
                sqlalchemy.select(Quiz).where(
                    Quiz.id == quiz_id,
                    Quiz.organizer_id == user_id,
                )
            )

            if quiz is None:
                return jsonify({
                    'error': 'quiz_not_found',
                    'message': 'Квиз не найден',
                }), 404

            db_session.delete(quiz)
            db_session.commit()

            return jsonify({
                'message': 'Квиз удалён',
                'quiz_id': quiz_id,
            }), 200

        except SQLAlchemyError:
            db_session.rollback()

            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось удалить квиз',
            }), 500