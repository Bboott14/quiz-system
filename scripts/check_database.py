import sqlite3
from pathlib import Path


database_path = Path('instance/quiz-system.sqlite')

if not database_path.exists():
    raise FileNotFoundError(
        f'База данных не найдена: {database_path.resolve()}'
    )

with sqlite3.connect(database_path) as connection:
    cursor = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ?
        ORDER BY name
        """,
        ('table',)
    )

    tables = [row[0] for row in cursor.fetchall()]

print('Таблицы базы данных:')

for table in tables:
    print(f'- {table}')