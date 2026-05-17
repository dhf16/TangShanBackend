from datetime import datetime

from flask import Blueprint, current_app, request

from app.common.response import error, success
from app.repositories.right_panel_repository import right_panel_repository

right_panel_bp = Blueprint("right_panel", __name__, url_prefix="/right-panel")

_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_FORMAT = "%Y-%m-%d"
_DATETIME_FORMATS = (_DATETIME_FORMAT, _DATE_FORMAT)


def _json_body():
    return request.get_json(silent=True) or {}


def _optional_str(value):
    return str(value or "").strip() or None


def _parse_datetime(value, field_name, end_of_day=False):
    if value is None:
        return None, None, None
    value = str(value).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == _DATE_FORMAT:
                if end_of_day:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                else:
                    parsed = parsed.replace(hour=0, minute=0, second=0)
            return parsed.strftime(_DATETIME_FORMAT), parsed, None
        except (ValueError, TypeError):
            continue
    return None, None, error(f"{field_name} format must be YYYY-MM-DD or YYYY-MM-DD HH:mm:ss", 400)


def _validate_date(value, field_name):
    if value in (None, ""):
        return None, None, None
    value = str(value).strip()
    try:
        parsed = datetime.strptime(value, _DATE_FORMAT)
        return parsed.strftime(_DATE_FORMAT), parsed, None
    except (ValueError, TypeError):
        return None, None, error(f"{field_name} format must be YYYY-MM-DD", 400)


def _require_time_range(req_data):
    begin_time = req_data.get("beginTime")
    end_time = req_data.get("endTime")
    if not begin_time or not end_time:
        return None, None, error("beginTime and endTime are required", 400)

    begin_time, begin_dt, err = _parse_datetime(begin_time, "beginTime")
    if err:
        return None, None, err
    end_time, end_dt, err = _parse_datetime(end_time, "endTime", end_of_day=True)
    if err:
        return None, None, err
    if begin_dt > end_dt:
        return None, None, error("beginTime must be earlier than or equal to endTime", 400)

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
    snapshot_date, _, err = _validate_date(req_data.get("snapshotDate"), "snapshotDate")
    if err:
        return None, err
    snapshot_start_date, start_dt, err = _validate_date(
        req_data.get("snapshotStartDate"), "snapshotStartDate"
    )
    if err:
        return None, err
    snapshot_end_date, end_dt, err = _validate_date(
        req_data.get("snapshotEndDate"), "snapshotEndDate"
    )
    if err:
        return None, err
    if start_dt and end_dt and start_dt > end_dt:
        return None, error("snapshotStartDate must be earlier than or equal to snapshotEndDate", 400)

    return {
        "snapshot_date": snapshot_date,
        "snapshot_start_date": snapshot_start_date,
        "snapshot_end_date": snapshot_end_date,
    }, None


@right_panel_bp.route("/county-warnings", methods=["POST"])
def right_panel_county_warnings():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.county_outage_status(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            **snapshot_filters,
        )
    except Exception:
        current_app.logger.exception("Failed to query county warnings")
        return error("Failed to query county warnings", 500)

    return success(data)


def _parse_int(req_data, key, default):
    try:
        return int(req_data.get(key, default))
    except (TypeError, ValueError):
        return default


@right_panel_bp.route("/fault-location", methods=["POST"])
def right_panel_fault_location():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.fault_location_summary(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            county_id=_optional_str(req_data.get("countyId")),
            dimension=_optional_str(req_data.get("dimension")),
            danger_threshold=_parse_int(req_data, "dangerThreshold", 5000),
            warning_threshold=_parse_int(req_data, "warningThreshold", 1000),
            **snapshot_filters,
        )
    except Exception:
        current_app.logger.exception("Failed to query fault location")
        return error("Failed to query fault location", 500)

    return success(data)


@right_panel_bp.route("/outage-scope", methods=["POST"])
def right_panel_outage_scope():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_scope(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            county_id=_optional_str(req_data.get("countyId")),
            **snapshot_filters,
        )
    except Exception:
        current_app.logger.exception("Failed to query outage scope")
        return error("Failed to query outage scope", 500)

    return success(data)


@right_panel_bp.route("/outage-events-summary", methods=["POST"])
def right_panel_outage_events_summary():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_events_summary(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            county_id=_optional_str(req_data.get("countyId")),
            keyword=_optional_str(req_data.get("keyword")),
            outage_nature=_optional_str(req_data.get("outageNature")),
            **snapshot_filters,
        )
    except Exception:
        current_app.logger.exception("Failed to query right panel outage events summary")
        return error("Failed to query right panel outage events summary", 500)

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

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_events_list(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            county_id=_optional_str(req_data.get("countyId")),
            keyword=_optional_str(req_data.get("keyword")),
            outage_nature=_optional_str(req_data.get("outageNature")),
            page=page,
            per_page=per_page,
            **snapshot_filters,
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

    snapshot_filters, err = _snapshot_filters(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.outage_chains(
            begin_time=begin_time,
            end_time=end_time,
            city_id=_optional_str(req_data.get("cityId")),
            county_id=_optional_str(req_data.get("countyId")),
            page=page,
            per_page=per_page,
            **snapshot_filters,
        )
    except Exception:
        current_app.logger.exception("Failed to query right panel outage chains")
        return error("Failed to query right panel outage chains", 500)

    return success(data)
