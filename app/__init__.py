from pathlib import Path

from flask import Flask

from config import Config
from app.extensions import socketio


def create_app():
    app = Flask(
        __name__,
        instance_relative_config=True
    )

    # Загружаем настройки из класса Config
    app.config.from_object(Config)

    # Создаём папку instance
    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True
    )

    # Создаём папку для загружаемых файлов
    Path(app.config['UPLOAD_FOLDER']).mkdir(
        parents=True,
        exist_ok=True
    )

    socketio.init_app(
        app,
        async_mode='threading'
    )

    from app.routes import main_blueprint
    app.register_blueprint(main_blueprint)

    from app import socket_events

    return app