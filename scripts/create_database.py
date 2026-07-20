from app import create_app
import app.database as database
from app.database import Base

# Импорт регистрирует модели в Base.metadata
from app import models


def create_database():
    create_app()

    if database.engine is None:
        raise RuntimeError('База данных не инициализирована')

    Base.metadata.create_all(
        bind=database.engine
    )

    print('Таблицы базы данных успешно созданы')


if __name__ == '__main__':
    create_database()