import uuid

import sqlalchemy

from app import create_app
import app.database as database
from app.models import (
    AnswerOption,
    GameRoom,
    Participant,
    ParticipantAnswer,
    Question,
    Quiz,
    SelectedOption,
    User,
)


def count_by_id(session, model, object_id):
    statement = sqlalchemy.select(
        sqlalchemy.func.count()
    ).select_from(model).where(
        model.id == object_id
    )

    return session.scalar(statement)


def test_cascade():
    create_app()

    if database.SessionLocal is None:
        raise RuntimeError(
            'Фабрика сессий SessionLocal не инициализирована'
        )

    with database.SessionLocal() as session:
        user = session.scalar(
            sqlalchemy.select(User).where(
                User.email == 'player@example.com'
            )
        )

        if user is None:
            raise RuntimeError(
                'Тестовый пользователь не найден. '
                'Сначала запустите scripts.seed_database'
            )

        suffix = uuid.uuid4().hex[:8]
        test_email = f'cascade-{suffix}@example.com'
        room_code = f'C-{suffix}'

        # Создаём отдельного пользователя-участника.
        participant_user = User(
            name='Пользователь для проверки каскада',
            email=test_email
        )
        participant_user.set_password('cascade-password')

        quiz = Quiz(
            organizer=user,
            title=f'Cascade test {suffix}',
            description='Временный квиз для проверки удаления',
            default_time_limit=30,
            status='ready'
        )

        question = Question(
            quiz=quiz,
            text='Временный вопрос',
            question_type='single_choice',
            time_limit=30,
            points=100,
            position=1
        )

        option = AnswerOption(
            question=question,
            text='Временный вариант',
            is_correct=True,
            position=1
        )

        room = GameRoom(
            quiz=quiz,
            code=room_code,
            status='waiting',
            current_question=question
        )

        participant = Participant(
            room=room,
            user=participant_user,
            nickname='Cascade player',
            score=100
        )

        answer = ParticipantAnswer(
            participant=participant,
            question=question,
            is_correct=True,
            awarded_points=100
        )

        selected = SelectedOption(
            participant_answer=answer,
            answer_option=option
        )

        session.add_all([
            participant_user,
            quiz,
            question,
            option,
            room,
            participant,
            answer,
            selected,
        ])

        session.commit()

        ids = {
            'quiz': quiz.id,
            'question': question.id,
            'option': option.id,
            'room': room.id,
            'participant': participant.id,
            'answer': answer.id,
            'participant_user': participant_user.id,
        }

        selected_key = (
            selected.participant_answer_id,
            selected.answer_option_id
        )

        print('Временные данные созданы:')
        print(ids)
        print(f'selected_option: {selected_key}')

        # Удаляем только квиз.
        session.delete(quiz)
        session.commit()

        checks = {
            'quizzes': count_by_id(
                session,
                Quiz,
                ids['quiz']
            ),
            'questions': count_by_id(
                session,
                Question,
                ids['question']
            ),
            'answer_options': count_by_id(
                session,
                AnswerOption,
                ids['option']
            ),
            'game_rooms': count_by_id(
                session,
                GameRoom,
                ids['room']
            ),
            'participants': count_by_id(
                session,
                Participant,
                ids['participant']
            ),
            'participant_answers': count_by_id(
                session,
                ParticipantAnswer,
                ids['answer']
            ),
        }

        selected_count = session.scalar(
            sqlalchemy.select(
                sqlalchemy.func.count()
            ).select_from(SelectedOption).where(
                SelectedOption.participant_answer_id
                == selected_key[0],
                SelectedOption.answer_option_id
                == selected_key[1]
            )
        )

        checks['selected_options'] = selected_count

        print('\nКоличество записей после удаления квиза:')

        for table, count in checks.items():
            print(f'- {table}: {count}')

        failed = {
            table: count
            for table, count in checks.items()
            if count != 0
        }

        if failed:
            raise AssertionError(
                'Каскадное удаление не сработало: '
                f'{failed}'
            )

        # Пользователь не должен удаляться вместе с квизом.
        participant_user_exists = count_by_id(
            session,
            User,
            ids['participant_user']
        )

        if participant_user_exists != 1:
            raise AssertionError(
                'Пользователь неожиданно был удалён'
            )

        # Удаляем оставшегося временного пользователя.
        session.delete(participant_user)
        session.commit()

        print('\nКаскадное удаление работает корректно.')


if __name__ == '__main__':
    test_cascade()