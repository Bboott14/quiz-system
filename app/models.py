from datetime import datetime, timezone

import sqlalchemy
from sqlalchemy.orm import relationship
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    name = sqlalchemy.Column(
        sqlalchemy.String(100),
        nullable=False
    )

    email = sqlalchemy.Column(
        sqlalchemy.String(255),
        nullable=False,
        unique=True,
        index=True
    )

    hashed_password = sqlalchemy.Column(
        sqlalchemy.String(255),
        nullable=False
    )

    created_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    quizzes = relationship(
        'Quiz',
        back_populates='organizer'
    )

    participations = relationship(
        'Participant',
        back_populates='user'
    )

    def set_password(self, password):
        self.hashed_password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.hashed_password,
            password
        )

    def __repr__(self):
        return f'<User id={self.id} email={self.email!r}>'


class Quiz(Base):
    __tablename__ = 'quizzes'

    __table_args__ = (
        sqlalchemy.CheckConstraint(
            "status IN ('draft', 'ready', 'archived')",
            name='check_quiz_status'
        ),
        sqlalchemy.CheckConstraint(
            'default_time_limit > 0',
            name='check_quiz_default_time_limit'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    organizer_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    title = sqlalchemy.Column(
        sqlalchemy.String(200),
        nullable=False
    )

    description = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=True
    )

    default_time_limit = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=30,
        nullable=False
    )

    status = sqlalchemy.Column(
        sqlalchemy.String(20),
        default='draft',
        nullable=False
    )

    created_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    organizer = relationship(
        'User',
        back_populates='quizzes'
    )

    questions = relationship(
        'Question',
        back_populates='quiz',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    game_rooms = relationship(
        'GameRoom',
        back_populates='quiz',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return f'<Quiz id={self.id} title={self.title!r}>'


class Question(Base):
    __tablename__ = 'questions'

    __table_args__ = (
        sqlalchemy.CheckConstraint(
            "question_type IN "
            "('single_choice', 'multiple_choice')",
            name='check_question_type'
        ),
        sqlalchemy.CheckConstraint(
            'time_limit IS NULL OR time_limit > 0',
            name='check_question_time_limit'
        ),
        sqlalchemy.CheckConstraint(
            'points >= 0',
            name='check_question_points'
        ),
        sqlalchemy.CheckConstraint(
            'position > 0',
            name='check_question_position'
        ),
        sqlalchemy.UniqueConstraint(
            'quiz_id',
            'position',
            name='uq_question_quiz_position'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    quiz_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'quizzes.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    text = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=False
    )

    image_path = sqlalchemy.Column(
        sqlalchemy.String(500),
        nullable=True
    )

    question_type = sqlalchemy.Column(
        sqlalchemy.String(30),
        default='single_choice',
        nullable=False
    )

    time_limit = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=True
    )

    points = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=100,
        nullable=False
    )

    position = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=False
    )

    quiz = relationship(
        'Quiz',
        back_populates='questions'
    )

    answer_options = relationship(
        'AnswerOption',
        back_populates='question',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    participant_answers = relationship(
        'ParticipantAnswer',
        back_populates='question',
        passive_deletes=True
    )

    current_in_rooms = relationship(
        'GameRoom',
        back_populates='current_question',
        foreign_keys='GameRoom.current_question_id'
    )

    def __repr__(self):
        return (
            f'<Question id={self.id} '
            f'position={self.position}>'
        )


class AnswerOption(Base):
    __tablename__ = 'answer_options'

    __table_args__ = (
        sqlalchemy.CheckConstraint(
            'position > 0',
            name='check_answer_option_position'
        ),
        sqlalchemy.UniqueConstraint(
            'question_id',
            'position',
            name='uq_answer_option_question_position'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    question_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'questions.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    text = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=False
    )

    is_correct = sqlalchemy.Column(
        sqlalchemy.Boolean,
        default=False,
        nullable=False
    )

    position = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=False
    )

    question = relationship(
        'Question',
        back_populates='answer_options'
    )

    selected_in_answers = relationship(
        'SelectedOption',
        back_populates='answer_option',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return (
            f'<AnswerOption id={self.id} '
            f'is_correct={self.is_correct}>'
        )


class GameRoom(Base):
    __tablename__ = 'game_rooms'

    __table_args__ = (
        sqlalchemy.CheckConstraint(
            "status IN ('waiting', 'running', 'finished')",
            name='check_game_room_status'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    quiz_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'quizzes.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    code = sqlalchemy.Column(
        sqlalchemy.String(20),
        nullable=False,
        unique=True,
        index=True
    )

    status = sqlalchemy.Column(
        sqlalchemy.String(20),
        default='waiting',
        nullable=False
    )

    current_question_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'questions.id',
            ondelete='SET NULL'
        ),
        nullable=True
    )

    started_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        nullable=True
    )

    finished_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        nullable=True
    )

    question_started_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        nullable=True
    )

    question_ends_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        nullable=True
    )

    quiz = relationship(
        'Quiz',
        back_populates='game_rooms'
    )

    current_question = relationship(
        'Question',
        back_populates='current_in_rooms',
        foreign_keys=[current_question_id]
    )

    participants = relationship(
        'Participant',
        back_populates='room',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return (
            f'<GameRoom id={self.id} '
            f'code={self.code!r} status={self.status!r}>'
        )


class Participant(Base):
    __tablename__ = 'participants'

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'room_id',
            'user_id',
            name='uq_participant_room_user'
        ),
        sqlalchemy.CheckConstraint(
            'score >= 0',
            name='check_participant_score'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    room_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'game_rooms.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    user_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    nickname = sqlalchemy.Column(
        sqlalchemy.String(100),
        nullable=False
    )

    score = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=0,
        nullable=False
    )

    joined_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    room = relationship(
        'GameRoom',
        back_populates='participants'
    )

    user = relationship(
        'User',
        back_populates='participations'
    )

    answers = relationship(
        'ParticipantAnswer',
        back_populates='participant',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return (
            f'<Participant id={self.id} '
            f'nickname={self.nickname!r}>'
        )


class ParticipantAnswer(Base):
    __tablename__ = 'participant_answers'

    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'participant_id',
            'question_id',
            name='uq_participant_answer_question'
        ),
        sqlalchemy.CheckConstraint(
            'response_time_ms IS NULL OR response_time_ms >= 0',
            name='check_answer_response_time'
        ),
        sqlalchemy.CheckConstraint(
            'awarded_points >= 0',
            name='check_answer_awarded_points'
        ),
    )

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True
    )

    participant_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'participants.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    question_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'questions.id',
            ondelete='CASCADE'
        ),
        nullable=False,
        index=True
    )

    submitted_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    response_time_ms = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=True
    )

    is_correct = sqlalchemy.Column(
        sqlalchemy.Boolean,
        default=False,
        nullable=False
    )

    awarded_points = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=0,
        nullable=False
    )

    participant = relationship(
        'Participant',
        back_populates='answers'
    )

    question = relationship(
        'Question',
        back_populates='participant_answers'
    )

    selected_options = relationship(
        'SelectedOption',
        back_populates='participant_answer',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return (
            f'<ParticipantAnswer id={self.id} '
            f'is_correct={self.is_correct}>'
        )


class SelectedOption(Base):
    __tablename__ = 'selected_options'

    participant_answer_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'participant_answers.id',
            ondelete='CASCADE'
        ),
        primary_key=True
    )

    answer_option_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'answer_options.id',
            ondelete='CASCADE'
        ),
        primary_key=True
    )

    participant_answer = relationship(
        'ParticipantAnswer',
        back_populates='selected_options'
    )

    answer_option = relationship(
        'AnswerOption',
        back_populates='selected_in_answers'
    )

    def __repr__(self):
        return (
            '<SelectedOption '
            f'answer={self.participant_answer_id} '
            f'option={self.answer_option_id}>'
        )