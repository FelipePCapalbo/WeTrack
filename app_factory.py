import logging
from logging.handlers import RotatingFileHandler

from flask import Flask

from config import Config
from extensions import init_extensions
from db import db, Database
from routes import register_routes


def _init_logging(app: Flask):
    handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.secret_key = app.config['SECRET_KEY']

    _init_logging(app)
    init_extensions(app)

    # Inicializa DB
    db.__init__(dsn=app.config['DATABASE_URL'])
    db.init_app(app)
    db.init_schema(app.logger)

    register_routes(app)

    return app


