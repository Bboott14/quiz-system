import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / 'instance' / 'quiz-system.sqlite'

class Config:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'development-secret-key'
    )
    DATABASE_URL = f'sqlite:///{DATABASE_PATH.as_posix()}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATABASE_PATH = BASE_DIR / 'instance' / 'quiz-system.sqlite'
    UPLOAD_FOLDER = BASE_DIR / 'instance' / 'uploads'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024