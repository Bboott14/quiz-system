document.addEventListener('DOMContentLoaded', () => {
    const statusElement = document.querySelector('#socket-status');
    const checkButton = document.querySelector('#socket-check');

    if (typeof io === 'undefined') {
        statusElement.textContent =
            'Не удалось загрузить Socket.IO Client';

        statusElement.className = 'status status--error';
        return;
    }

    const socket = io();

    socket.on('connect', () => {
        statusElement.textContent =
            'Соединение с сервером установлено';

        statusElement.className = 'status status--success';
    });

    socket.on('disconnect', () => {
        statusElement.textContent =
            'Соединение с сервером потеряно';

        statusElement.className = 'status status--error';
    });

    socket.on('server_status', (data) => {
        console.log(data.message);
    });

    socket.on('server_pong', (data) => {
        statusElement.textContent = data.message;
        statusElement.className = 'status status--success';
    });

    checkButton.addEventListener('click', () => {
        socket.emit('client_ping');
    });
});