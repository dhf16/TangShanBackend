from datetime import datetime

from flask import Blueprint, current_app, request

from app.common.response import error, success
from app.repositories.right_panel_repository import right_panel_repository

right_panel_bp = Blueprint("right_panel", __name__, url_prefix="/right-panel")

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _json_body():
    return request.get_json(silent=True) or {}


def _optional_str(value):
    return str(value or "").strip() or None


def _validate_datetime(value, field_name):
    if value is None:
        return None, None
    for fmt in _DATETIME_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return value, None
        except (ValueError, TypeError):
            continue
    return None, error(f"{field_name} format must be YYYY-MM-DD or YYYY-MM-DD HH:mm:ss", 400)


def _require_time_range(req_data):
    begin_time = req_data.get("beginTime")
    end_time = req_data.get("endTime")
    if not begin_time or not end_time:
        return None, None, error("beginTime and endTime are required", 400)

    begin_time, err = _validate_datetime(begin_time, "beginTime")
    if err:
        return None, None, err
    end_time, err = _validate_datetime(end_time, "endTime")
    if err:
        return None, None, err

    return begin_time, end_time, None


def _parse_pagination(req_data):
    try:
        page = int(req_data.get("page", 1))
        per_page = int(req_data.get("perPage", 20))
    except (TypeError, ValueError):
        return None, None, error("page and perPage must be integers", 400)

    if page < 1:
        return None, None, error("page must be greater than or equal to 1", 400)
    if per_page < 1 or per_page > 500:
        return None, None, error("perPage must be between 1 and 500", 400)

    return page, per_page, None


def _snapshot_filters(req_data):
    return {
        "snapshot_date": req_data.get("snapshotDate"),
        "snapshot_start_date": req_data.get("snapshotStartDate"),
        "snapshot_end_date": req_data.get("snapshotEndDate"),
    }


@right_panel_bp.route("/overview", methods=["POST"])
def right_panel_overview():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.overview(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            city_id=_optional_str(req_data.get("cityId")),
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query right panel overview")
        return error("Failed to query right panel overview", 500)

    return success(data)


@right_panel_bp.route("/outage-events", methods=["POST"])
def right_panel_outage_events():
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
        current_app.logger.exception("Failed to query right panel outage events")
        return error("Failed to query right panel outage events", 500)

    return success(data)


@right_panel_bp.route("/outage-event-detail", methods=["POST"])
def right_panel_outage_event_detail():
    req_data = _json_body()
    outage_number = _optional_str(req_data.get("outageNumber"))
    if not outage_number:
        return error("outageNumber is required", 400)

    try:
        data = right_panel_repository.outage_event_detail(outage_number)
    except Exception:
        current_app.logger.exception("Failed to query right panel outage event detail")
        return error("Failed to query right panel outage event detail", 500)

    if not data:
        return error("Outage event not found", 404)
    return success(data)


@right_panel_bp.route("/outage-chains", methods=["POST"])
def right_panel_outage_chains():
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
        current_app.logger.exception("Failed to query right panel outage chains")
        return error("Failed to query right panel outage chains", 500)

    return success(data)
