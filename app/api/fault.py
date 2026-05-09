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


def _bar_count(summary, key):
    bars = summary.get("bars") if isinstance(summary, dict) else []
    for item in bars:
        if item.get("key") == key:
            return int(item.get("count") or 0)
    return 0


@fault_bp.route("/summary", methods=["POST"])
def fault_summary():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    try:
        feeder = right_panel_repository.fault_location_by_entity(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            entity_type="feeder",
            **_snapshot_filters(req_data),
        )
        substation = right_panel_repository.fault_location_by_entity(
            begin_time=begin_time,
            end_time=end_time,
            county_id=_optional_str(req_data.get("countyId")),
            entity_type="substation",
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query fault summary")
        return error("Failed to query fault summary", 500)

    return success({
        "highImpact": {"count": _bar_count(feeder, "danger")},
        "mediumImpact": {"count": _bar_count(feeder, "warning")},
        "lowImpact": {"count": _bar_count(feeder, "safe")},
        "modes": {
            "feeder": feeder,
            "substation": substation,
        },
    })


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
