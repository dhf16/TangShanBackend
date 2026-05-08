import os

def _env_int(name, default):
    return int(os.environ.get(name, default))


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # MySQL settings used by the app and utility scripts.
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = _env_int("MYSQL_PORT", 3306)
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "tangshan_backend")
    MYSQL_CHARSET = "utf8mb4"
    MYSQL_USER_SCORE_TABLE = os.environ.get("MYSQL_USER_SCORE_TABLE", "outage_user_full")

    # Token
    TOKEN_STRATEGY = os.environ.get("TOKEN_STRATEGY", "none")
    TOKEN_HEADER_NAME = os.environ.get("TOKEN_HEADER_NAME", "x-token")
    TOKEN_HEADER_PREFIX = os.environ.get("TOKEN_HEADER_PREFIX", "")

    # API
    API_USER_DETAIL_URL = os.environ.get(
        "API_USER_DETAIL_URL",
        "http://154.12.39.249:5000/realMeasCenter/dsOutageAnalysis/outageEvent/queryOutageUserDetail",
    )
    API_OUTAGE_LIST_URL = os.environ.get(
        "API_OUTAGE_LIST_URL",
        "http://154.12.39.249:5000/realMeasCenter/dsOutageAnalysis/outageEvent/queryOutageList",
    )
    API_OUTAGE_DETAIL_URL = os.environ.get(
        "API_OUTAGE_DETAIL_URL",
        "http://154.12.39.249:5000/realMeasCenter/dsOutageAnalysis/outageEvent/queryOutageDetail",
    )
    API_START_DATE = os.environ.get("API_START_DATE", "2025-01-01")
    API_END_DATE = os.environ.get("API_END_DATE", "2026-04-30")
    API_PER_PAGE = _env_int("API_PER_PAGE", 300)
    API_MAX_PAGES = _env_int("API_MAX_PAGES", 50)


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


def validate_config(app):
    if not app.config.get("DEBUG") and app.config.get("SECRET_KEY") == "dev-secret-key":
        raise RuntimeError("SECRET_KEY must be set in production")

    if app.config.get("ENV_NAME") == "production":
        required = ("SECRET_KEY", "MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Missing required production env vars: {', '.join(missing)}")


class TestingConfig(BaseConfig):
    TESTING = True
    MYSQL_DATABASE = "tangshan_backend_test"
