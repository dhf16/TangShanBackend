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

fault_bp = Blueprint("fault", __name__, url_prefix="/fault")


@fault_bp.route("/summary", methods=["POST"])
def fault_summary():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    try:
        data = right_panel_repository.fault_summary(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query fault summary")
        return error("Failed to query fault summary", 500)

    return success(data)


@fault_bp.route("/event-list", methods=["POST"])
def fault_event_list():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    page, per_page, err = _parse_pagination(req_data)
    if err:
        return err

    dimension = (_optional_str(req_data.get("dimension")) or "line").lower()
    if dimension not in ("line", "feeder", "substation", "equipment"):
        return error("dimension must be one of line, feeder, substation, equipment", 400)

    try:
        data = right_panel_repository.fault_events(
            begin_time=begin_time,
            end_time=end_time,
            dimension=dimension,
            county_id=_optional_str(req_data.get("countyId")),
            keyword=_optional_str(req_data.get("keyword")),
            outage_nature=_optional_str(req_data.get("outageNature")),
            page=page,
            per_page=per_page,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query fault event list")
        return error("Failed to query fault event list", 500)

    return success(data)


@fault_bp.route("/equipment-list", methods=["POST"])
def fault_equipment_list():
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
        current_app.logger.exception("Failed to query fault equipment list")
        return error("Failed to query fault equipment list", 500)

    return success(data)
