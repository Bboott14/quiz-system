from pathlib import Path

from flask import Flask

from config import Config
from app.database import init_database
from app.extensions import socketio


def create_app():
    app = Flask(
        __name__,
        instance_relative_config=True
    )

    app.config.from_object(Config)

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True
    )

    Path(app.config['UPLOAD_FOLDER']).mkdir(
        parents=True,
        exist_ok=True
    )

    init_database(
        app.config['DATABASE_URL']
    )

    socketio.init_app(
        app,
        async_mode='threading'
    )
    from app.routes import main_blueprint
    from app.quiz_routes import quiz_blueprint
    from app.question_routes import question_blueprint
    from app.room_routes import room_blueprint
    from app.game_routes import game_blueprint

    app.register_blueprint(main_blueprint)
    app.register_blueprint(quiz_blueprint)
    app.register_blueprint(question_blueprint)
    app.register_blueprint(room_blueprint)
    app.register_blueprint(game_blueprint)
    from app import socket_events

    return app