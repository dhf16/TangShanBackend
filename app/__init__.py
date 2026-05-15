import logging
import os

from flask import Flask, jsonify

from app.config import validate_config


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV", "development")
    config_name = config_name.lower()

    app = Flask(__name__)
    config_map = {
        "development": "app.config.DevelopmentConfig",
        "production": "app.config.ProductionConfig",
        "testing": "app.config.TestingConfig",
    }
    app.config.from_object(config_map.get(config_name, config_map["development"]))
    app.config["ENV_NAME"] = config_name
    validate_config(app)

    _configure_logging(app)

    from app.api import api_bp
    from app.repositories.county_repository import county_repository
    from app.repositories.right_panel_repository import right_panel_repository

    app.register_blueprint(api_bp)
    county_repository.init_app(app)
    right_panel_repository.init_app(app)

    _register_error_handlers(app)

    return app


def _configure_logging(app):
    level = logging.DEBUG if app.debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)
    app.logger.setLevel(level)


def _register_error_handlers(app):
    from app.common.response import error

    @app.errorhandler(404)
    def not_found(e):
        return error("Resource not found", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return error("Method not allowed", 405)

    @app.errorhandler(500)
    def internal_error(e):
        return error("Internal server error", 500)
