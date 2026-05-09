from flask import Blueprint, current_app

from app.common.response import error, success
from app.repositories.right_panel_repository import right_panel_repository
from app.api.right_panel import (
    _json_body,
    _optional_str,
    _parse_pagination,
    _require_time_range,
    _snapshot_filters,
)

outage_scope_bp = Blueprint("outage_scope", __name__, url_prefix="/outage-scope")


@outage_scope_bp.route("/summary", methods=["POST"])
def outage_scope_summary():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_scope_summary(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query outage scope summary")
        return error("Failed to query outage scope summary", 500)

    return success(data)


@outage_scope_bp.route("/event-list", methods=["POST"])
def outage_scope_event_list():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    page, per_page, err = _parse_pagination(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_events(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            keyword=_optional_str(req_data.get("keyword")),
            outage_nature=_optional_str(req_data.get("outageNature")),
            page=page,
            per_page=per_page,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query outage scope event list")
        return error("Failed to query outage scope event list", 500)

    return success(data)


@outage_scope_bp.route("/chains", methods=["POST"])
def outage_scope_chains():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    page, per_page, err = _parse_pagination(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_chains(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            page=page,
            per_page=per_page,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query outage scope chains")
        return error("Failed to query outage scope chains", 500)

    return success(data)
