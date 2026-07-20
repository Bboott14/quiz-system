import sqlalchemy
from flask import Blueprint, jsonify, request, session as flask_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

import app.database as database
from app.models import AnswerOption, Question, Quiz


question_blueprint = Blueprint(
    'questions',
    __name__,
    url_prefix='/api'
)


ALLOWED_QUESTION_TYPES = {
    'single_choice',
    'multiple_choice',
}


def serialize_option(option):
    return {
        'id': option.id,
        'question_id': option.question_id,
        'text': option.text,
        'is_correct': option.is_correct,
        'position': option.position,
    }


def serialize_question(question):
    options = sorted(
        question.answer_options,
        key=lambda option: option.position
    )

    return {
        'id': question.id,
        'quiz_id': question.quiz_id,
        'text': question.text,
        'image_path': question.image_path,
        'question_type': question.question_type,
        'time_limit': question.time_limit,
        'points': question.points,
        'position': question.position,
        'answer_options': [
            serialize_option(option)
            for option in options
        ],
    }


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


def get_owned_quiz(db_session, quiz_id, user_id):
    return db_session.scalar(
        sqlalchemy.select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.organizer_id == user_id,
        )
    )


def get_owned_question(
    db_session,
    question_id,
    user_id,
    load_options=False
):
    statement = (
        sqlalchemy.select(Question)
        .join(Quiz, Question.quiz_id == Quiz.id)
        .where(
            Question.id == question_id,
            Quiz.organizer_id == user_id,
        )
    )

    if load_options:
        statement = statement.options(
            selectinload(Question.answer_options)
        )

    return db_session.scalar(statement)


def get_owned_option(db_session, option_id, user_id):
    return db_session.scalar(
        sqlalchemy.select(AnswerOption)
        .join(
            Question,
            AnswerOption.question_id == Question.id
        )
        .join(
            Quiz,
            Question.quiz_id == Quiz.id
        )
        .where(
            AnswerOption.id == option_id,
            Quiz.organizer_id == user_id,
        )
    )


def validate_positive_integer(
    value,
    field_name,
    *,
    allow_none=False,
    allow_zero=False
):
    if value is None and allow_none:
        return None

    if isinstance(value, bool):
        return f'{field_name} должно быть целым числом'

    try:
        number = int(value)
    except (TypeError, ValueError):
        return f'{field_name} должно быть целым числом'

    minimum = 0 if allow_zero else 1

    if number < minimum:
        if allow_zero:
            return f'{field_name} не может быть отрицательным'

        return f'{field_name} должно быть больше нуля'

    return None


def validate_question_data(data, partial=False):
    errors = {}

    if not isinstance(data, dict):
        return {
            'body': 'Тело запроса должно быть JSON-объектом'
        }

    if not partial or 'text' in data:
        text = str(data.get('text', '')).strip()

        if not text:
            errors['text'] = 'Укажите текст вопроса'

    if 'question_type' in data:
        question_type = data.get('question_type')

        if question_type not in ALLOWED_QUESTION_TYPES:
            errors['question_type'] = (
                'Допустимые типы: '
                'single_choice, multiple_choice'
            )

    if 'time_limit' in data:
        error = validate_positive_integer(
            data.get('time_limit'),
            'Время вопроса',
            allow_none=True
        )

        if error:
            errors['time_limit'] = error

    if 'points' in data:
        error = validate_positive_integer(
            data.get('points'),
            'Количество баллов',
            allow_zero=True
        )

        if error:
            errors['points'] = error

    if 'position' in data:
        error = validate_positive_integer(
            data.get('position'),
            'Позиция'
        )

        if error:
            errors['position'] = error

    if 'image_path' in data:
        image_path = data.get('image_path')

        if (
            image_path is not None
            and not isinstance(image_path, str)
        ):
            errors['image_path'] = (
                'Путь к изображению должен быть строкой или null'
            )

    return errors


def validate_option_data(data, partial=False):
    errors = {}

    if not isinstance(data, dict):
        return {
            'body': 'Тело запроса должно быть JSON-объектом'
        }

    if not partial or 'text' in data:
        text = str(data.get('text', '')).strip()

        if not text:
            errors['text'] = 'Укажите текст варианта ответа'

    if 'is_correct' in data:
        if not isinstance(data.get('is_correct'), bool):
            errors['is_correct'] = (
                'Поле is_correct должно быть true или false'
            )

    if 'position' in data:
        error = validate_positive_integer(
            data.get('position'),
            'Позиция'
        )

        if error:
            errors['position'] = error

    return errors


# ---------------------------------------------------------
# Добавить вопрос
# ---------------------------------------------------------

@question_blueprint.route(
    '/quizzes/<int:quiz_id>/questions',
    methods=['POST']
)
def create_question(quiz_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    errors = validate_question_data(data)

    answer_options = data.get('answer_options', [])

    if not isinstance(answer_options, list):
        errors['answer_options'] = (
            'Поле answer_options должно быть массивом'
        )
    else:
        option_errors = {}

        for index, option_data in enumerate(answer_options):
            current_errors = validate_option_data(option_data)

            if current_errors:
                option_errors[str(index)] = current_errors

        if option_errors:
            errors['answer_options'] = option_errors

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    with database.SessionLocal() as db_session:
        try:
            quiz = get_owned_quiz(
                db_session,
                quiz_id,
                user_id
            )

            if quiz is None:
                return jsonify({
                    'error': 'quiz_not_found',
                    'message': 'Квиз не найден',
                }), 404

            position = data.get('position')

            if position is None:
                maximum_position = db_session.scalar(
                    sqlalchemy.select(
                        sqlalchemy.func.max(Question.position)
                    ).where(
                        Question.quiz_id == quiz.id
                    )
                )

                position = (maximum_position or 0) + 1

            question = Question(
                quiz=quiz,
                text=str(data['text']).strip(),
                image_path=data.get('image_path'),
                question_type=data.get(
                    'question_type',
                    'single_choice'
                ),
                time_limit=data.get('time_limit'),
                points=int(data.get('points', 100)),
                position=int(position),
            )

            for index, option_data in enumerate(answer_options):
                option_position = option_data.get(
                    'position',
                    index + 1
                )

                AnswerOption(
                    question=question,
                    text=str(option_data['text']).strip(),
                    is_correct=option_data.get(
                        'is_correct',
                        False
                    ),
                    position=int(option_position),
                )

            db_session.add(question)
            db_session.commit()

            question = get_owned_question(
                db_session,
                question.id,
                user_id,
                load_options=True
            )

            return jsonify({
                'message': 'Вопрос добавлен',
                'question': serialize_question(question),
            }), 201

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_question_data',
                'message': (
                    'Некорректные данные или позиция уже занята'
                ),
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось добавить вопрос'
            )


# ---------------------------------------------------------
# Изменить вопрос
# ---------------------------------------------------------

@question_blueprint.route(
    '/questions/<int:question_id>',
    methods=['PATCH']
)
def update_question(question_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    allowed_fields = {
        'text',
        'image_path',
        'question_type',
        'time_limit',
        'points',
        'position',
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

    errors = validate_question_data(data, partial=True)

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    with database.SessionLocal() as db_session:
        try:
            question = get_owned_question(
                db_session,
                question_id,
                user_id,
                load_options=True
            )

            if question is None:
                return jsonify({
                    'error': 'question_not_found',
                    'message': 'Вопрос не найден',
                }), 404

            if 'text' in data:
                question.text = str(data['text']).strip()

            if 'image_path' in data:
                question.image_path = data['image_path']

            if 'question_type' in data:
                question.question_type = data[
                    'question_type'
                ]

            if 'time_limit' in data:
                value = data['time_limit']
                question.time_limit = (
                    int(value)
                    if value is not None
                    else None
                )

            if 'points' in data:
                question.points = int(data['points'])

            if 'position' in data:
                question.position = int(data['position'])

            db_session.commit()

            return jsonify({
                'message': 'Вопрос обновлён',
                'question': serialize_question(question),
            }), 200

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_question_data',
                'message': (
                    'Некорректные данные или позиция уже занята'
                ),
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось обновить вопрос'
            )


# ---------------------------------------------------------
# Удалить вопрос
# ---------------------------------------------------------

@question_blueprint.route(
    '/questions/<int:question_id>',
    methods=['DELETE']
)
def delete_question(question_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    with database.SessionLocal() as db_session:
        try:
            question = get_owned_question(
                db_session,
                question_id,
                user_id
            )

            if question is None:
                return jsonify({
                    'error': 'question_not_found',
                    'message': 'Вопрос не найден',
                }), 404

            db_session.delete(question)
            db_session.commit()

            return jsonify({
                'message': 'Вопрос удалён',
                'question_id': question_id,
            }), 200

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось удалить вопрос'
            )


# ---------------------------------------------------------
# Добавить вариант ответа
# ---------------------------------------------------------

@question_blueprint.route(
    '/questions/<int:question_id>/options',
    methods=['POST']
)
def create_option(question_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    errors = validate_option_data(data)

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    with database.SessionLocal() as db_session:
        try:
            question = get_owned_question(
                db_session,
                question_id,
                user_id
            )

            if question is None:
                return jsonify({
                    'error': 'question_not_found',
                    'message': 'Вопрос не найден',
                }), 404

            position = data.get('position')

            if position is None:
                maximum_position = db_session.scalar(
                    sqlalchemy.select(
                        sqlalchemy.func.max(
                            AnswerOption.position
                        )
                    ).where(
                        AnswerOption.question_id
                        == question.id
                    )
                )

                position = (maximum_position or 0) + 1

            option = AnswerOption(
                question=question,
                text=str(data['text']).strip(),
                is_correct=data.get('is_correct', False),
                position=int(position),
            )

            db_session.add(option)
            db_session.commit()

            return jsonify({
                'message': 'Вариант ответа добавлен',
                'answer_option': serialize_option(option),
            }), 201

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_option_data',
                'message': (
                    'Некорректные данные или позиция уже занята'
                ),
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось добавить вариант ответа'
            )


# ---------------------------------------------------------
# Изменить вариант ответа
# ---------------------------------------------------------

@question_blueprint.route(
    '/options/<int:option_id>',
    methods=['PATCH']
)
def update_option(option_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON',
        }), 400

    allowed_fields = {
        'text',
        'is_correct',
        'position',
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

    errors = validate_option_data(data, partial=True)

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors,
        }), 400

    with database.SessionLocal() as db_session:
        try:
            option = get_owned_option(
                db_session,
                option_id,
                user_id
            )

            if option is None:
                return jsonify({
                    'error': 'option_not_found',
                    'message': 'Вариант ответа не найден',
                }), 404

            if 'text' in data:
                option.text = str(data['text']).strip()

            if 'is_correct' in data:
                option.is_correct = data['is_correct']

            if 'position' in data:
                option.position = int(data['position'])

            db_session.commit()

            return jsonify({
                'message': 'Вариант ответа обновлён',
                'answer_option': serialize_option(option),
            }), 200

        except (IntegrityError, ValueError):
            db_session.rollback()

            return jsonify({
                'error': 'invalid_option_data',
                'message': (
                    'Некорректные данные или позиция уже занята'
                ),
            }), 400

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось обновить вариант ответа'
            )


# ---------------------------------------------------------
# Удалить вариант ответа
# ---------------------------------------------------------

@question_blueprint.route(
    '/options/<int:option_id>',
    methods=['DELETE']
)
def delete_option(option_id):
    user_id = flask_session.get('user_id')

    if user_id is None:
        return authentication_error()

    with database.SessionLocal() as db_session:
        try:
            option = get_owned_option(
                db_session,
                option_id,
                user_id
            )

            if option is None:
                return jsonify({
                    'error': 'option_not_found',
                    'message': 'Вариант ответа не найден',
                }), 404

            db_session.delete(option)
            db_session.commit()

            return jsonify({
                'message': 'Вариант ответа удалён',
                'option_id': option_id,
            }), 200

        except SQLAlchemyError:
            db_session.rollback()

            return database_error(
                'Не удалось удалить вариант ответа'
            )