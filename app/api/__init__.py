from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

# ------------------------------------------------------------------
# health
# ------------------------------------------------------------------

@api_bp.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------
# register sub-blueprints
# ------------------------------------------------------------------

from app.api.county import county_bp  # noqa: E402
from app.api.right_panel import right_panel_bp  # noqa: E402

api_bp.register_blueprint(county_bp)
api_bp.register_blueprint(right_panel_bp)
