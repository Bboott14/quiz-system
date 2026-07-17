from flask import Blueprint, jsonify, render_template


main_blueprint = Blueprint('main', __name__)


@main_blueprint.route('/')
def index():
    return render_template('index.html')


@main_blueprint.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'application': 'quiz-system'
    })