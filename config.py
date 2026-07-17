import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'development-secret-key'
    )

    DATABASE_PATH = BASE_DIR / 'instance' / 'quiz-system.sqlite'
    UPLOAD_FOLDER = BASE_DIR / 'instance' / 'uploads'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024