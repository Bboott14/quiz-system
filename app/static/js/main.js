document.addEventListener('DOMContentLoaded', () => {
    const ROOM_STORAGE_KEY = 'quiz-room';

    const state = {
        user: null,
        roomCode: null,
        room: null,
        role: null,
        currentQuestion: null,
        socket: null,
        timerId: null,
        pollingId: null,
        answerSubmitted: false,
    };

    const elements = {
        notifications: document.querySelector('#notifications'),
        socketStatus: document.querySelector('#socket-status'),

        authSection: document.querySelector('#auth-section'),
        dashboardSection: document.querySelector(
            '#dashboard-section'
        ),
        roomSection: document.querySelector('#room-section'),
        questionSection: document.querySelector(
            '#question-section'
        ),
        resultsSection: document.querySelector(
            '#results-section'
        ),

        loginForm: document.querySelector('#login-form'),
        registerForm: document.querySelector('#register-form'),
        logoutButton: document.querySelector('#logout-button'),
        currentUser: document.querySelector('#current-user'),

        createQuizForm: document.querySelector(
            '#create-quiz-form'
        ),
        refreshQuizzes: document.querySelector(
            '#refresh-quizzes'
        ),
        quizList: document.querySelector('#quiz-list'),

        joinRoomForm: document.querySelector('#join-room-form'),
        roomCode: document.querySelector('#room-code'),
        roomStatus: document.querySelector('#room-status'),
        participantList: document.querySelector(
            '#participant-list'
        ),

        organizerControls: document.querySelector(
            '#organizer-controls'
        ),
        startGameButton: document.querySelector(
            '#start-game-button'
        ),
        nextQuestionButton: document.querySelector(
            '#next-question-button'
        ),
        leaveRoomButton: document.querySelector(
            '#leave-room-button'
        ),

        questionPosition: document.querySelector(
            '#question-position'
        ),
        questionTimer: document.querySelector(
            '#question-timer'
        ),
        questionPoints: document.querySelector(
            '#question-points'
        ),
        questionText: document.querySelector('#question-text'),
        answerForm: document.querySelector('#answer-form'),
        answerOptions: document.querySelector(
            '#answer-options'
        ),
        submitAnswerButton: document.querySelector(
            '#submit-answer-button'
        ),
        answerResult: document.querySelector(
            '#answer-result'
        ),

        leaderboard: document.querySelector('#leaderboard'),
        resultsBackButton: document.querySelector(
            '#results-back-button'
        ),
    };

    // -----------------------------------------------------
    // Общие вспомогательные функции
    // -----------------------------------------------------

    function show(element) {
        if (element) {
            element.classList.remove('hidden');
        }
    }

    function hide(element) {
        if (element) {
            element.classList.add('hidden');
        }
    }

    function escapeHtml(value) {
        const container = document.createElement('div');

        container.textContent =
            value === null || value === undefined
                ? ''
                : String(value);

        return container.innerHTML;
    }

    function notify(message, type = 'success') {
        const notification = document.createElement('div');

        notification.className =
            `notification notification--${type}`;

        notification.textContent = message;

        elements.notifications.appendChild(notification);

        window.setTimeout(() => {
            notification.remove();
        }, 5000);
    }

    function extractErrorMessage(data, fallback) {
        if (!data) {
            return fallback;
        }

        if (data.message) {
            return data.message;
        }

        if (
            data.fields &&
            typeof data.fields === 'object'
        ) {
            return Object.values(data.fields).join('. ');
        }

        return data.error || fallback;
    }

    async function api(url, options = {}) {
        const config = {
            credentials: 'same-origin',
            ...options,
        };

        if (
            config.body !== undefined &&
            config.body !== null &&
            typeof config.body !== 'string'
        ) {
            config.headers = {
                'Content-Type':
                    'application/json; charset=utf-8',
                ...(config.headers || {}),
            };

            config.body = JSON.stringify(config.body);
        }

        const response = await fetch(url, config);

        let data = null;

        try {
            data = await response.json();
        } catch (error) {
            data = null;
        }

        if (!response.ok) {
            console.error(
                'Ошибка API:',
                response.status,
                url,
                data
            );

            const requestError = new Error(
                extractErrorMessage(
                    data,
                    `Ошибка HTTP ${response.status}`
                )
            );

            requestError.status = response.status;
            requestError.data = data;

            throw requestError;
        }

        return data;
    }

    // -----------------------------------------------------
    // Сохранение комнаты
    // -----------------------------------------------------

    function saveRoomState() {
        if (!state.roomCode || !state.role) {
            return;
        }

        sessionStorage.setItem(
            ROOM_STORAGE_KEY,
            JSON.stringify({
                code: state.roomCode,
                role: state.role,
            })
        );
    }

    function getSavedRoomState() {
        const value = sessionStorage.getItem(
            ROOM_STORAGE_KEY
        );

        if (!value) {
            return null;
        }

        try {
            const room = JSON.parse(value);

            if (!room.code || !room.role) {
                clearSavedRoomState();
                return null;
            }

            return {
                code: String(room.code).trim().toUpperCase(),
                role: room.role,
            };
        } catch (error) {
            clearSavedRoomState();
            return null;
        }
    }

    function clearSavedRoomState() {
        sessionStorage.removeItem(ROOM_STORAGE_KEY);
    }

    // -----------------------------------------------------
    // Переключение разделов
    // -----------------------------------------------------

    function setView(name) {
        hide(elements.authSection);
        hide(elements.dashboardSection);
        hide(elements.roomSection);
        hide(elements.questionSection);
        hide(elements.resultsSection);

        if (name === 'auth') {
            show(elements.authSection);
        }

        if (name === 'dashboard') {
            show(elements.dashboardSection);
        }

        if (name === 'room') {
            show(elements.roomSection);
        }

        if (name === 'game') {
            show(elements.roomSection);
            show(elements.questionSection);
        }

        if (name === 'results') {
            show(elements.resultsSection);
        }
    }

    function setUser(user, loadDashboard = true) {
        state.user = user;

        if (!user) {
            elements.currentUser.textContent = '';
            setView('auth');
            return;
        }

        elements.currentUser.textContent =
            `${user.name} (${user.email})`;

        if (loadDashboard) {
            setView('dashboard');
            loadQuizzes();
        }
    }

    // -----------------------------------------------------
    // Авторизация
    // -----------------------------------------------------

    async function initializeAuthentication() {
        try {
            const data = await api('/api/auth/me');

            setUser(data.user);

            const savedRoom = getSavedRoomState();

            if (savedRoom) {
                enterRoom(
                    savedRoom.code,
                    savedRoom.role
                );
            }
        } catch (error) {
            clearSavedRoomState();

            if (error.status !== 401) {
                notify(error.message, 'error');
            }

            setUser(null);
        }
    }

    elements.loginForm.addEventListener(
        'submit',
        async (event) => {
            event.preventDefault();

            const formData = new FormData(
                elements.loginForm
            );

            try {
                const data = await api('/api/auth/login', {
                    method: 'POST',
                    body: {
                        email: formData.get('email'),
                        password: formData.get('password'),
                    },
                });

                elements.loginForm.reset();

                setUser(data.user);
                reconnectSocket();

                notify('Вход выполнен');
            } catch (error) {
                notify(error.message, 'error');
            }
        }
    );

    elements.registerForm.addEventListener(
        'submit',
        async (event) => {
            event.preventDefault();

            const formData = new FormData(
                elements.registerForm
            );

            try {
                const data = await api(
                    '/api/auth/register',
                    {
                        method: 'POST',
                        body: {
                            name: formData.get('name'),
                            email: formData.get('email'),
                            password:
                                formData.get('password'),
                        },
                    }
                );

                elements.registerForm.reset();

                setUser(data.user);
                reconnectSocket();

                notify('Регистрация выполнена');
            } catch (error) {
                notify(error.message, 'error');
            }
        }
    );

    elements.logoutButton.addEventListener(
        'click',
        async () => {
            const previousRoomCode = state.roomCode;

            try {
                await api('/api/auth/logout', {
                    method: 'POST',
                });
            } catch (error) {
                notify(error.message, 'error');
                return;
            }

            if (
                state.socket &&
                state.socket.connected &&
                previousRoomCode
            ) {
                state.socket.emit('unsubscribe_room', {
                    code: previousRoomCode,
                });
            }

            clearSavedRoomState();
            stopPolling();
            stopTimer();

            state.user = null;
            state.roomCode = null;
            state.room = null;
            state.role = null;
            state.currentQuestion = null;
            state.answerSubmitted = false;

            hide(elements.questionSection);
            hide(elements.resultsSection);
            hide(elements.organizerControls);

            setUser(null);
            reconnectSocket();

            notify('Вы вышли из системы');
        }
    );

    // -----------------------------------------------------
    // Квизы
    // -----------------------------------------------------

    async function loadQuizzes() {
        if (!state.user) {
            return;
        }

        elements.quizList.innerHTML =
            '<p class="muted">Загрузка...</p>';

        try {
            const data = await api('/api/quizzes');
            const quizzes = data.quizzes || [];

            if (!quizzes.length) {
                elements.quizList.innerHTML =
                    '<p class="muted">' +
                    'Квизы ещё не созданы.' +
                    '</p>';

                return;
            }

            elements.quizList.innerHTML = quizzes
                .map((quiz) => `
                    <article class="quiz-item">
                        <div>
                            <strong>
                                ${escapeHtml(quiz.title)}
                            </strong>

                            <div class="muted">
                                ID: ${quiz.id};
                                статус:
                                ${escapeHtml(quiz.status)}
                            </div>
                        </div>

                        <button
                            type="button"
                            class="create-room-button"
                            data-quiz-id="${quiz.id}"
                        >
                            Создать комнату
                        </button>
                    </article>
                `)
                .join('');
        } catch (error) {
            elements.quizList.innerHTML = '';

            if (error.status !== 401) {
                notify(error.message, 'error');
            }
        }
    }

    elements.refreshQuizzes.addEventListener(
        'click',
        loadQuizzes
    );

    elements.createQuizForm.addEventListener(
        'submit',
        async (event) => {
            event.preventDefault();

            const formData = new FormData(
                elements.createQuizForm
            );

            try {
                await api('/api/quizzes', {
                    method: 'POST',
                    body: {
                        title: formData.get('title'),
                        description:
                            formData.get('description'),
                        default_time_limit: Number(
                            formData.get(
                                'default_time_limit'
                            )
                        ),
                    },
                });

                elements.createQuizForm.reset();

                const timeInput =
                    elements.createQuizForm.querySelector(
                        '[name="default_time_limit"]'
                    );

                if (timeInput) {
                    timeInput.value = 30;
                }

                notify(
                    'Квиз создан. Перед созданием комнаты ' +
                    'добавьте в него вопросы.'
                );

                await loadQuizzes();
            } catch (error) {
                notify(error.message, 'error');
            }
        }
    );

    elements.quizList.addEventListener(
        'click',
        async (event) => {
            const button = event.target.closest(
                '.create-room-button'
            );

            if (!button) {
                return;
            }

            button.disabled = true;

            try {
                const quizId = button.dataset.quizId;

                const data = await api(
                    `/api/quizzes/${quizId}/rooms`,
                    {
                        method: 'POST',
                        body: {},
                    }
                );

                const room = data.room || data;
                const code = room.code;

                if (!code) {
                    throw new Error(
                        'Сервер не вернул код комнаты'
                    );
                }

                enterRoom(code, 'organizer', room);

                notify(`Комната ${code} создана`);
            } catch (error) {
                notify(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        }
    );

    // -----------------------------------------------------
    // Вход в комнату
    // -----------------------------------------------------

    elements.joinRoomForm.addEventListener(
        'submit',
        async (event) => {
            event.preventDefault();

            const formData = new FormData(
                elements.joinRoomForm
            );

            const code = String(
                formData.get('code')
            ).trim().toUpperCase();

            const nickname = String(
                formData.get('nickname')
            ).trim();

            try {
                const data = await api(
                    `/api/rooms/${encodeURIComponent(
                        code
                    )}/join`,
                    {
                        method: 'POST',
                        body: {
                            nickname,
                        },
                    }
                );

                elements.joinRoomForm.reset();

                enterRoom(
                    code,
                    'participant',
                    data.room || null
                );

                notify(
                    'Вы присоединились к комнате'
                );
            } catch (error) {
                /*
                 * Если сервер сообщает, что пользователь
                 * уже присоединился, пробуем восстановить
                 * комнату без повторного join.
                 */
                if (error.status === 409) {
                    try {
                        const roomData = await api(
                            `/api/rooms/${encodeURIComponent(
                                code
                            )}`
                        );

                        const room =
                            roomData.room || roomData;

                        enterRoom(
                            code,
                            roomData.is_organizer
                                ? 'organizer'
                                : 'participant',
                            room
                        );

                        notify(
                            'Комната восстановлена'
                        );

                        return;
                    } catch (roomError) {
                        notify(
                            error.message,
                            'error'
                        );

                        return;
                    }
                }

                notify(error.message, 'error');
            }
        }
    );

    function enterRoom(code, role, room = null) {
        stopPolling();
        stopTimer();

        state.roomCode = String(code)
            .trim()
            .toUpperCase();

        state.role = role;
        state.room = room;
        state.currentQuestion = null;
        state.answerSubmitted = false;

        saveRoomState();

        elements.roomCode.textContent =
            state.roomCode;

        if (state.role === 'organizer') {
            show(elements.organizerControls);
        } else {
            hide(elements.organizerControls);
        }

        renderRoom(room);
        setView('room');
        subscribeToRoom();
        startPolling();
    }

    function leaveRoom() {
        const previousRoomCode = state.roomCode;

        clearSavedRoomState();

        if (
            state.socket &&
            state.socket.connected &&
            previousRoomCode
        ) {
            state.socket.emit('unsubscribe_room', {
                code: previousRoomCode,
            });
        }

        stopPolling();
        stopTimer();

        state.roomCode = null;
        state.room = null;
        state.role = null;
        state.currentQuestion = null;
        state.answerSubmitted = false;

        elements.roomCode.textContent = '';
        elements.roomStatus.textContent = 'waiting';
        elements.participantList.innerHTML = '';

        hide(elements.questionSection);
        hide(elements.resultsSection);
        hide(elements.organizerControls);

        if (state.user) {
            setView('dashboard');
            loadQuizzes();
        } else {
            setView('auth');
        }
    }

    elements.leaveRoomButton.addEventListener(
        'click',
        leaveRoom
    );

    elements.resultsBackButton.addEventListener(
        'click',
        leaveRoom
    );

    // -----------------------------------------------------
    // Отображение комнаты
    // -----------------------------------------------------

    function renderRoom(room) {
        if (!room) {
            elements.roomStatus.textContent = 'waiting';

            elements.participantList.innerHTML =
                '<p class="muted">' +
                'Ожидание участников...' +
                '</p>';

            return;
        }

        state.room = room;

        elements.roomStatus.textContent =
            room.status || 'waiting';

        const participants = room.participants || [];

        if (!participants.length) {
            elements.participantList.innerHTML =
                '<p class="muted">' +
                'Участников пока нет.' +
                '</p>';
        } else {
            elements.participantList.innerHTML =
                participants
                    .map((participant) => `
                        <div class="participant-item">
                            <span>
                                ${escapeHtml(
                                    participant.nickname
                                )}
                            </span>

                            <strong>
                                ${participant.score || 0}
                                баллов
                            </strong>
                        </div>
                    `)
                    .join('');
        }

        if (state.role !== 'organizer') {
            hide(elements.organizerControls);
            return;
        }

        show(elements.organizerControls);

        if (room.status === 'waiting') {
            show(elements.startGameButton);
            hide(elements.nextQuestionButton);
        } else if (room.status === 'running') {
            hide(elements.startGameButton);
            show(elements.nextQuestionButton);
        } else {
            hide(elements.startGameButton);
            hide(elements.nextQuestionButton);
        }
    }

    function extractRoomAndQuestion(data) {
        const room = data.room || data;

        const question =
            data.question ||
            data.current_question ||
            room.current_question ||
            null;

        return {
            room,
            question,
        };
    }

    async function refreshRoom() {
        if (!state.roomCode || !state.user) {
            return;
        }

        const requestedCode = state.roomCode;

        try {
            const data = await api(
                `/api/rooms/${encodeURIComponent(
                    requestedCode
                )}`
            );

            /*
             * Пока запрос выполнялся, пользователь мог
             * перейти в другую комнату.
             */
            if (state.roomCode !== requestedCode) {
                return;
            }

            const {
                room,
                question,
            } = extractRoomAndQuestion(data);

            if (data.is_organizer === true) {
                state.role = 'organizer';
                saveRoomState();
                show(elements.organizerControls);
            } else if (
                data.is_organizer === false &&
                state.role !== 'participant'
            ) {
                state.role = 'participant';
                saveRoomState();
                hide(elements.organizerControls);
            }

            renderRoom(room);

            if (
                room.status === 'running' &&
                question &&
                (
                    !state.currentQuestion ||
                    state.currentQuestion.id !==
                        question.id
                )
            ) {
                displayQuestion(question, room);
            }

            if (room.status === 'finished') {
                await loadResults();
            }
        } catch (error) {
            if (state.roomCode !== requestedCode) {
                return;
            }

            if (error.status === 401) {
                stopPolling();
                stopTimer();
                clearSavedRoomState();

                state.roomCode = null;
                state.room = null;
                state.role = null;
                state.currentQuestion = null;

                setUser(null);
                return;
            }

            if (error.status === 403) {
                stopPolling();
                stopTimer();
                clearSavedRoomState();

                state.roomCode = null;
                state.room = null;
                state.role = null;
                state.currentQuestion = null;

                notify(
                    'У вас нет доступа к этой комнате',
                    'error'
                );

                setView('dashboard');
                return;
            }

            if (error.status === 404) {
                notify(
                    'Комната больше не существует',
                    'error'
                );

                leaveRoom();
                return;
            }

            console.error(
                'Не удалось обновить комнату:',
                error
            );
        }
    }

    function startPolling() {
        stopPolling();

        refreshRoom();

        state.pollingId = window.setInterval(() => {
            refreshRoom();
        }, 3000);
    }

    function stopPolling() {
        if (state.pollingId !== null) {
            window.clearInterval(state.pollingId);
            state.pollingId = null;
        }
    }

    // -----------------------------------------------------
    // Запуск игры
    // -----------------------------------------------------

    elements.startGameButton.addEventListener(
        'click',
        async () => {
            if (
                !state.roomCode ||
                state.role !== 'organizer'
            ) {
                notify(
                    'Запустить игру может только организатор',
                    'error'
                );

                return;
            }

            elements.startGameButton.disabled = true;

            try {
                const data = await api(
                    `/api/rooms/${encodeURIComponent(
                        state.roomCode
                    )}/start`,
                    {
                        method: 'POST',
                        body: {},
                    }
                );

                if (data.room) {
                    renderRoom(data.room);
                }

                if (data.question) {
                    displayQuestion(
                        data.question,
                        data.room || state.room
                    );
                } else {
                    await refreshRoom();
                }

                notify('Игра запущена');
            } catch (error) {
                notify(error.message, 'error');
            } finally {
                elements.startGameButton.disabled = false;
            }
        }
    );

    // -----------------------------------------------------
    // Следующий вопрос
    // -----------------------------------------------------

    elements.nextQuestionButton.addEventListener(
        'click',
        async () => {
            if (
                !state.roomCode ||
                state.role !== 'organizer'
            ) {
                notify(
                    'Переключать вопросы может ' +
                    'только организатор',
                    'error'
                );

                return;
            }

            elements.nextQuestionButton.disabled = true;

            try {
                const data = await api(
                    `/api/rooms/${encodeURIComponent(
                        state.roomCode
                    )}/next`,
                    {
                        method: 'POST',
                        body: {},
                    }
                );

                if (
                    data.status === 'finished' ||
                    data.room?.status === 'finished'
                ) {
                    if (data.leaderboard) {
                        renderLeaderboard(
                            data.leaderboard
                        );

                        setView('results');
                        stopPolling();
                        stopTimer();
                    } else {
                        await loadResults();
                    }

                    return;
                }

                if (data.leaderboard) {
                    renderLeaderboard(
                        data.leaderboard
                    );
                }

                if (data.question) {
                    displayQuestion(
                        data.question,
                        data.room || state.room
                    );
                } else {
                    await refreshRoom();
                }
            } catch (error) {
                notify(error.message, 'error');
            } finally {
                elements.nextQuestionButton.disabled =
                    false;
            }
        }
    );

    // -----------------------------------------------------
    // Вопрос
    // -----------------------------------------------------

    function displayQuestion(question, room = null) {
        if (!question) {
            return;
        }

        stopTimer();

        state.currentQuestion = question;
        state.answerSubmitted = false;

        const position =
            question.position || '';

        const points =
            question.points || 0;

        const options =
            question.answer_options || [];

        elements.questionPosition.textContent =
            position
                ? `Вопрос ${position}`
                : 'Вопрос';

        elements.questionPoints.textContent =
            points;

        elements.questionText.textContent =
            question.text || '';

        elements.answerResult.textContent = '';
        elements.answerResult.className = 'hidden';

        const inputType =
            question.question_type ===
            'multiple_choice'
                ? 'checkbox'
                : 'radio';

        if (options.length) {
            elements.answerOptions.innerHTML = options
                .map((option) => `
                    <label class="answer-option">
                        <input
                            type="${inputType}"
                            name="answer-option"
                            value="${option.id}"
                        >

                        <span>
                            ${escapeHtml(option.text)}
                        </span>
                    </label>
                `)
                .join('');
        } else {
            elements.answerOptions.innerHTML =
                '<p class="muted">' +
                'Варианты ответа отсутствуют.' +
                '</p>';
        }

        if (state.role === 'organizer') {
            hide(elements.answerForm);
        } else {
            show(elements.answerForm);

            elements.submitAnswerButton.disabled =
                false;

            elements.submitAnswerButton.textContent =
                'Отправить ответ';
        }

        const endsAt =
            question.ends_at ||
            room?.question_ends_at ||
            state.room?.question_ends_at ||
            null;

        startTimer(
            endsAt,
            question.time_limit
        );

        setView('game');
    }

    // -----------------------------------------------------
    // Таймер
    // -----------------------------------------------------

    function parseServerDate(value) {
        if (!value) {
            return null;
        }

        let normalized = String(value);

        const containsTimezone =
            /Z$/i.test(normalized) ||
            /[+-]\d{2}:\d{2}$/.test(normalized);

        if (!containsTimezone) {
            normalized += 'Z';
        }

        const date = new Date(normalized);

        return Number.isNaN(date.getTime())
            ? null
            : date;
    }

    function startTimer(
        endsAt,
        fallbackSeconds = null
    ) {
        stopTimer();

        let endDate = parseServerDate(endsAt);

        if (
            !endDate &&
            fallbackSeconds !== null &&
            fallbackSeconds !== undefined
        ) {
            endDate = new Date(
                Date.now() +
                Number(fallbackSeconds) * 1000
            );
        }

        if (!endDate) {
            elements.questionTimer.textContent = '--';
            return;
        }

        function updateTimer() {
            const remainingMilliseconds =
                endDate.getTime() - Date.now();

            const seconds = Math.max(
                0,
                Math.ceil(
                    remainingMilliseconds / 1000
                )
            );

            elements.questionTimer.textContent =
                `${seconds} с`;

            if (seconds <= 0) {
                stopTimer();

                if (
                    !state.answerSubmitted &&
                    state.role !== 'organizer'
                ) {
                    elements.submitAnswerButton.disabled =
                        true;
                }
            }
        }

        updateTimer();

        state.timerId = window.setInterval(
            updateTimer,
            250
        );
    }

    function stopTimer() {
        if (state.timerId !== null) {
            window.clearInterval(state.timerId);
            state.timerId = null;
        }
    }

    // -----------------------------------------------------
    // Отправка ответа
    // -----------------------------------------------------

    elements.answerForm.addEventListener(
        'submit',
        async (event) => {
            event.preventDefault();

            if (
                state.role === 'organizer' ||
                !state.roomCode ||
                !state.currentQuestion ||
                state.answerSubmitted
            ) {
                return;
            }

            const selectedOptions = [
                ...elements.answerOptions.querySelectorAll(
                    'input:checked'
                ),
            ];

            const optionIds = selectedOptions.map(
                (input) => Number(input.value)
            );

            if (!optionIds.length) {
                notify(
                    'Выберите вариант ответа',
                    'error'
                );

                return;
            }

            elements.submitAnswerButton.disabled = true;

            try {
                const data = await api(
                    `/api/rooms/${encodeURIComponent(
                        state.roomCode
                    )}/answers`,
                    {
                        method: 'POST',
                        body: {
                            option_ids: optionIds,
                        },
                    }
                );

                state.answerSubmitted = true;

                elements.answerOptions
                    .querySelectorAll('input')
                    .forEach((input) => {
                        input.disabled = true;
                    });

                const answer =
                    data.answer ||
                    data.result ||
                    data;

                const participant =
                    data.participant || {};

                const isCorrect =
                    answer.is_correct === true;

                const awardedPoints =
                    answer.awarded_points ??
                    answer.points ??
                    0;

                const totalScore =
                    participant.score ??
                    data.score ??
                    null;

                elements.answerResult.className =
                    isCorrect
                        ? (
                            'answer-result ' +
                            'answer-result--correct'
                        )
                        : (
                            'answer-result ' +
                            'answer-result--wrong'
                        );

                if (isCorrect) {
                    elements.answerResult.textContent =
                        totalScore !== null
                            ? (
                                `Правильно! ` +
                                `+${awardedPoints} баллов. ` +
                                `Всего: ${totalScore}.`
                            )
                            : (
                                `Правильно! ` +
                                `+${awardedPoints} баллов.`
                            );
                } else {
                    elements.answerResult.textContent =
                        `Неправильно. Начислено: ` +
                        `${awardedPoints} баллов.`;
                }
            } catch (error) {
                elements.submitAnswerButton.disabled =
                    false;

                notify(error.message, 'error');
            }
        }
    );

    // -----------------------------------------------------
    // Результаты
    // -----------------------------------------------------

    async function loadResults() {
        if (!state.roomCode) {
            return;
        }

        stopTimer();

        try {
            const data = await api(
                `/api/rooms/${encodeURIComponent(
                    state.roomCode
                )}/results`
            );

            renderLeaderboard(
                data.leaderboard || []
            );

            setView('results');
            stopPolling();
        } catch (error) {
            if (error.status !== 409) {
                notify(error.message, 'error');
            }
        }
    }

    function renderLeaderboard(leaderboard) {
        if (!leaderboard.length) {
            elements.leaderboard.innerHTML =
                '<p class="muted">' +
                'Результатов пока нет.' +
                '</p>';

            return;
        }

        elements.leaderboard.innerHTML =
            leaderboard
                .map((item) => `
                    <div class="leaderboard-item">
                        <strong class="leaderboard-rank">
                            ${item.rank}
                        </strong>

                        <span>
                            ${escapeHtml(item.nickname)}
                        </span>

                        <strong>
                            ${item.score} баллов
                        </strong>
                    </div>
                `)
                .join('');
    }

    // -----------------------------------------------------
    // Socket.IO
    // -----------------------------------------------------

    function initializeSocket() {
        if (typeof io === 'undefined') {
            elements.socketStatus.textContent =
                'Socket.IO Client не загружен';

            elements.socketStatus.className =
                'status status--error';

            return;
        }

        state.socket = io();

        state.socket.on('connect', () => {
            elements.socketStatus.textContent =
                'Соединение установлено';

            elements.socketStatus.className =
                'status status--success';

            subscribeToRoom();
        });

        state.socket.on('disconnect', () => {
            elements.socketStatus.textContent =
                'Соединение потеряно';

            elements.socketStatus.className =
                'status status--error';
        });

        state.socket.on('server_status', (data) => {
            console.log(data.message);
        });

        state.socket.on(
            'room_subscribed',
            (data) => {
                console.log(
                    'Подписка на комнату:',
                    data
                );

                if (
                    !state.roomCode ||
                    String(data.code).toUpperCase() !==
                        state.roomCode
                ) {
                    return;
                }

                state.role = data.is_organizer
                    ? 'organizer'
                    : 'participant';

                saveRoomState();

                if (state.role === 'organizer') {
                    show(elements.organizerControls);
                } else {
                    hide(elements.organizerControls);
                }

                refreshRoom();
            }
        );

        state.socket.on(
            'room_unsubscribed',
            (data) => {
                console.log(
                    'Отписка от комнаты:',
                    data.code
                );
            }
        );

        state.socket.on('room_error', (data) => {
            notify(
                data.message || 'Ошибка Socket.IO',
                'error'
            );
        });

        state.socket.on(
            'participant_joined',
            (data) => {
                if (
                    !data.room_code ||
                    data.room_code === state.roomCode
                ) {
                    refreshRoom();
                }
            }
        );

        state.socket.on('game_started', (data) => {
            if (
                data.room_code &&
                data.room_code !== state.roomCode
            ) {
                return;
            }

            if (data.room) {
                renderRoom(data.room);
            }

            const question =
                data.question ||
                data.room?.current_question ||
                null;

            if (question) {
                displayQuestion(
                    question,
                    data.room || state.room
                );
            } else {
                refreshRoom();
            }
        });

        state.socket.on(
            'question_started',
            (data) => {
                if (
                    data.room_code &&
                    data.room_code !== state.roomCode
                ) {
                    return;
                }

                if (data.question) {
                    displayQuestion(
                        data.question,
                        state.room
                    );
                } else {
                    refreshRoom();
                }
            }
        );

        state.socket.on(
            'question_finished',
            (data) => {
                if (
                    data.room_code &&
                    data.room_code !== state.roomCode
                ) {
                    return;
                }

                if (data.leaderboard) {
                    renderLeaderboard(
                        data.leaderboard
                    );
                }
            }
        );

        state.socket.on(
            'answer_received',
            (data) => {
                if (
                    data.room_code &&
                    data.room_code !== state.roomCode
                ) {
                    return;
                }

                if (state.role === 'organizer') {
                    refreshRoom();
                }
            }
        );

        state.socket.on(
            'game_finished',
            (data) => {
                if (
                    data.room_code &&
                    data.room_code !== state.roomCode
                ) {
                    return;
                }

                stopTimer();
                stopPolling();

                if (data.leaderboard) {
                    renderLeaderboard(
                        data.leaderboard
                    );

                    setView('results');
                } else {
                    loadResults();
                }
            }
        );
    }

    function reconnectSocket() {
        if (!state.socket) {
            return;
        }

        state.socket.disconnect();
        state.socket.connect();
    }

    function subscribeToRoom() {
        if (
            !state.socket ||
            !state.socket.connected ||
            !state.roomCode
        ) {
            return;
        }

        state.socket.emit('subscribe_room', {
            code: state.roomCode,
        });
    }

    // -----------------------------------------------------
    // Запуск клиента
    // -----------------------------------------------------

    initializeSocket();
    initializeAuthentication();
});