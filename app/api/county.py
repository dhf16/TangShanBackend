from datetime import datetime

from flask import Blueprint, current_app, request

from app.common.response import error, success
from app.repositories.county_repository import county_repository

county_bp = Blueprint("county", __name__, url_prefix="/county")

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


@county_bp.route("/list", methods=["POST"])
def county_list():
    req_data = _json_body()
    city_id = _optional_str(req_data.get("cityId"))

    try:
        counties = county_repository.list_counties(city_id=city_id)
    except Exception:
        current_app.logger.exception("Failed to query counties")
        return error("Failed to query counties", 500)

    return success({"list": counties})


@county_bp.route("/stats", methods=["POST"])
def county_stats():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    county_id = _optional_str(req_data.get("countyId"))
    common = {
        "begin_time": begin_time,
        "end_time": end_time,
        **_snapshot_filters(req_data),
    }

    try:
        if county_id:
            stats = county_repository.stats_for_county(county_id=county_id, **common)
            return success(stats)

        rows = county_repository.stats_by_county(**common)
    except Exception:
        current_app.logger.exception("Failed to query county stats")
        return error("Failed to query county stats", 500)

    return success({
        "summary": {
            "totalUsers": sum(r["totalUsers"] for r in rows),
            "keyUsers": sum(r["keyUsers"] for r in rows),
            "sensitiveUsers": sum(r["sensitiveUsers"] for r in rows),
            "normalUsers": sum(r["normalUsers"] for r in rows),
        },
        "list": rows,
    })


@county_bp.route("/detail-stats", methods=["POST"])
def county_detail_stats():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    common = {
        "rdt_county_id": _optional_str(req_data.get("countyId")),
        "begin_time": begin_time,
        "end_time": end_time,
        **_snapshot_filters(req_data),
    }

    try:
        key_by_trade = county_repository.aggregate_distribution_by_industry(
            user_level="key", **common
        )
        sensitive_by_trade = county_repository.aggregate_distribution_by_industry(
            user_level="sensitive", **common
        )
        outage_by_nature = county_repository.aggregate_distribution_by_outage_nature(
            user_level="key_sensitive", **common
        )

        key_total = sum(r.get("userCount", 0) for r in key_by_trade)
        sensitive_total = sum(r.get("userCount", 0) for r in sensitive_by_trade)
        nature_total = sum(r.get("userCount", 0) for r in outage_by_nature)

        nature_distribution = [
            {
                **r,
                "percentage": round(r.get("userCount", 0) / nature_total * 100, 1) if nature_total else 0,
            }
            for r in outage_by_nature
        ]
    except Exception:
        current_app.logger.exception("Failed to query detail stats")
        return error("Failed to query detail stats", 500)

    return success({
        "summary": {
            "keyUsers": key_total,
            "sensitiveUsers": sensitive_total,
            "total": key_total + sensitive_total,
        },
        "keyUserByTrade": key_by_trade,
        "sensitiveUserByTrade": sensitive_by_trade,
        "outageNatureDistribution": nature_distribution,
    })


@county_bp.route("/user-list", methods=["POST"])
def county_user_list():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    user_level = req_data.get("userLevel")
    if user_level not in (None, "", "all", "key", "sensitive"):
        return error("userLevel must be one of all/key/sensitive", 400)
    if user_level == "all" or not user_level:
        user_level = None

    page, per_page, err = _parse_pagination(req_data)
    if err:
        return err

    try:
        rows, total = county_repository.query_identified_users(
            page=page,
            per_page=per_page,
            user_level=user_level,
            keyword=_optional_str(req_data.get("keyword")),
            rdt_county_id=_optional_str(req_data.get("countyId")),
            begin_time=begin_time,
            end_time=end_time,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query user list")
        return error("Failed to query user list", 500)

    users = [
        {
            "consNo": row.get("consNo", ""),
            "consName": row.get("consName", ""),
            "countyName": row.get("rdtCountyName", ""),
            "tradeName": row.get("tradeName", ""),
            "outageNature": row.get("outageNature", ""),
            "isKeyUser": row.get("isKeyUser", False),
            "isSensitiveUser": row.get("isSensitiveUser", False),
        }
        for row in rows
    ]

    return success({
        "total": total,
        "page": page,
        "perPage": per_page,
        "list": users,
    })


@county_bp.route("/trend", methods=["POST"])
def county_trend():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    try:
        points = county_repository.trend_by_time(
            begin_time=begin_time,
            end_time=end_time,
            rdt_county_id=_optional_str(req_data.get("countyId")),
        )
    except ValueError as e:
        return error(str(e), 400)
    except Exception:
        current_app.logger.exception("Failed to query trend data")
        return error("Failed to query trend data", 500)

    return success({"points": points})


@county_bp.route("/bar-chart", methods=["POST"])
def county_bar_chart():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    county_id = _optional_str(req_data.get("countyId"))
    common = {
        "begin_time": begin_time,
        "end_time": end_time,
        **_snapshot_filters(req_data),
    }

    try:
        if county_id:
            rows = county_repository.bar_chart_by_maint_group(
                county_id=county_id, **common
            )
        else:
            rows = county_repository.bar_chart_by_county(**common)

        total = sum(r["keyUsers"] + r["sensitiveUsers"] for r in rows)

        items = []
        for r in rows:
            name = r.get("countyName") or r.get("maintGroupName", "")
            item_id = r.get("countyId") or r.get("maintGroupId", "")
            items.append({
                "name": name,
                "id": item_id,
                "keyUsers": r["keyUsers"],
                "sensitiveUsers": r["sensitiveUsers"],
                "keyPercentage": round(r["keyUsers"] / total * 100, 1) if total else 0,
                "sensitivePercentage": round(r["sensitiveUsers"] / total * 100, 1) if total else 0,
            })
    except Exception:
        current_app.logger.exception("Failed to query bar chart data")
        return error("Failed to query bar chart data", 500)

    return success({"total": total, "list": items})
