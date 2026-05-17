from flask import Blueprint

from app.common.response import success

api_bp = Blueprint("api", __name__, url_prefix="/api")

# ------------------------------------------------------------------
# health
# ------------------------------------------------------------------

@api_bp.route("/health", methods=["GET"])
def health():
    return success({"status": "ok"})


# ------------------------------------------------------------------
# register sub-blueprints
# ------------------------------------------------------------------

from app.api.county import county_bp  # noqa: E402

api_bp.register_blueprint(county_bp)
