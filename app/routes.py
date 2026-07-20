import sqlalchemy
from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import app.database as database
from app.models import User


main_blueprint = Blueprint('main', __name__)


@main_blueprint.route('/')
def index():
    return render_template('index.html')


@main_blueprint.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'application': 'quiz-system'
    })


# ---------------------------------------------------------
# Регистрация
# ---------------------------------------------------------

@main_blueprint.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON'
        }), 400

    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    errors = {}

    if not name:
        errors['name'] = 'Укажите имя'
    elif len(name) > 100:
        errors['name'] = 'Имя не должно быть длиннее 100 символов'

    if not email:
        errors['email'] = 'Укажите email'
    elif '@' not in email:
        errors['email'] = 'Некорректный email'
    elif len(email) > 255:
        errors['email'] = 'Email слишком длинный'

    if not password:
        errors['password'] = 'Укажите пароль'
    elif len(password) < 6:
        errors['password'] = (
            'Пароль должен содержать минимум 6 символов'
        )

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors
        }), 400

    if database.SessionLocal is None:
        return jsonify({
            'error': 'database_not_initialized'
        }), 500

    with database.SessionLocal() as db_session:
        try:
            existing_user = db_session.scalar(
                sqlalchemy.select(User).where(
                    User.email == email
                )
            )

            if existing_user is not None:
                return jsonify({
                    'error': 'email_already_exists',
                    'message': 'Пользователь с таким email уже существует'
                }), 409

            user = User(
                name=name,
                email=email
            )
            user.set_password(password)

            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)

            user_id = user.id
            user_name = user.name
            user_email = user.email
            created_at = user.created_at.isoformat()

            # Авторизуем пользователя сразу после регистрации
            session.clear()
            session['user_id'] = user_id

            return jsonify({
                'message': 'Пользователь зарегистрирован',
                'user': {
                    'id': user_id,
                    'name': user_name,
                    'email': user_email,
                    'created_at': created_at
                }
            }), 201

        except IntegrityError:
            db_session.rollback()

            return jsonify({
                'error': 'email_already_exists',
                'message': 'Пользователь с таким email уже существует'
            }), 409

        except SQLAlchemyError:
            db_session.rollback()

            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось зарегистрировать пользователя'
            }), 500


# ---------------------------------------------------------
# Вход
# ---------------------------------------------------------

@main_blueprint.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            'error': 'invalid_json',
            'message': 'Тело запроса должно содержать JSON'
        }), 400

    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    errors = {}

    if not email:
        errors['email'] = 'Укажите email'

    if not password:
        errors['password'] = 'Укажите пароль'

    if errors:
        return jsonify({
            'error': 'validation_error',
            'fields': errors
        }), 400

    if database.SessionLocal is None:
        return jsonify({
            'error': 'database_not_initialized'
        }), 500

    with database.SessionLocal() as db_session:
        try:
            user = db_session.scalar(
                sqlalchemy.select(User).where(
                    User.email == email
                )
            )

            # Одинаковое сообщение для неправильного email и пароля
            if user is None or not user.check_password(password):
                return jsonify({
                    'error': 'invalid_credentials',
                    'message': 'Неверный email или пароль'
                }), 401

            user_id = user.id
            user_name = user.name
            user_email = user.email

            session.clear()
            session['user_id'] = user_id

            return jsonify({
                'message': 'Вход выполнен',
                'user': {
                    'id': user_id,
                    'name': user_name,
                    'email': user_email
                }
            }), 200

        except SQLAlchemyError:
            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось выполнить вход'
            }), 500


# ---------------------------------------------------------
# Текущий пользователь
# ---------------------------------------------------------

@main_blueprint.route('/api/auth/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')

    if user_id is None:
        return jsonify({
            'error': 'authentication_required',
            'message': 'Требуется авторизация'
        }), 401

    if database.SessionLocal is None:
        return jsonify({
            'error': 'database_not_initialized'
        }), 500

    with database.SessionLocal() as db_session:
        try:
            user = db_session.get(User, user_id)

            if user is None:
                session.clear()

                return jsonify({
                    'error': 'user_not_found',
                    'message': 'Пользователь не найден'
                }), 401

            return jsonify({
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                    'created_at': user.created_at.isoformat()
                }
            }), 200

        except SQLAlchemyError:
            return jsonify({
                'error': 'database_error',
                'message': 'Не удалось получить пользователя'
            }), 500


# ---------------------------------------------------------
# Выход
# ---------------------------------------------------------

@main_blueprint.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()

    return jsonify({
        'message': 'Выход выполнен'
    }), 200