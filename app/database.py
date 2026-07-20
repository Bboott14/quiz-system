from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


@event.listens_for(Engine, 'connect')
def enable_sqlite_foreign_keys(
    connection,
    connection_record
):
    cursor = connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


def init_database(database_url):
    global engine
    global SessionLocal

    engine = create_engine(
        database_url,
        echo=False
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False
    )