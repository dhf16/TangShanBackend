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
    city_id = _optional_str(req_data.get("cityId"))
    if county_id and city_id:
        return error("countyId and cityId are mutually exclusive", 400)

    common = {
        "begin_time": begin_time,
        "end_time": end_time,
        **_snapshot_filters(req_data),
    }

    try:
        if county_id:
            summary = county_repository.stats_for_county(county_id=county_id, **common)
            rows = county_repository.bar_chart_by_maint_group(
                county_id=county_id, **common
            )
            total = sum(r["keyUsers"] + r["sensitiveUsers"] for r in rows)
            items = [
                {
                    "name": r["maintGroupName"],
                    "id": r["maintGroupId"],
                    "keyUsers": r["keyUsers"],
                    "sensitiveUsers": r["sensitiveUsers"],
                    "keyPercentage": round(r["keyUsers"] / total * 100, 1) if total else 0,
                    "sensitivePercentage": round(r["sensitiveUsers"] / total * 100, 1) if total else 0,
                }
                for r in rows
            ]
        else:
            rows = county_repository.stats_by_county(city_id=city_id, **common)
            summary = {
                "totalUsers": sum(r["totalUsers"] for r in rows),
                "keyUsers": sum(r["keyUsers"] for r in rows),
                "sensitiveUsers": sum(r["sensitiveUsers"] for r in rows),
                "normalUsers": sum(r["normalUsers"] for r in rows),
            }
            total = summary["keyUsers"] + summary["sensitiveUsers"]
            items = [
                {
                    "name": r["countyName"],
                    "id": r["countyId"],
                    "totalUsers": r["totalUsers"],
                    "keyUsers": r["keyUsers"],
                    "sensitiveUsers": r["sensitiveUsers"],
                    "normalUsers": r["normalUsers"],
                    "keyPercentage": round(r["keyUsers"] / total * 100, 1) if total else 0,
                    "sensitivePercentage": round(r["sensitiveUsers"] / total * 100, 1) if total else 0,
                }
                for r in rows
            ]
    except Exception:
        current_app.logger.exception("Failed to query county stats")
        return error("Failed to query county stats", 500)

    return success({"summary": summary, "list": items})


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
    if user_level not in (None, "", "all", "key", "sensitive", "key_sensitive"):
        return error("userLevel must be one of all/key/sensitive/key_sensitive", 400)
    if user_level == "all" or not user_level:
        user_level = None

    outage_count = req_data.get("outageCount")
    if outage_count is not None:
        outage_count = str(outage_count).strip()
        if outage_count not in ("1", "2", "3+"):
            return error("outageCount must be one of 1/2/3+", 400)
    else:
        outage_count = None

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
            outage_count_filter=outage_count,
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
            "outageNumber": row.get("outageNumber", ""),
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


@county_bp.route("/outage-freq", methods=["POST"])
def county_outage_freq():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    county_id = _optional_str(req_data.get("countyId"))
    common = {
        "begin_time": begin_time,
        "end_time": end_time,
        "rdt_county_id": county_id,
        **_snapshot_filters(req_data),
    }

    try:
        key_rows = county_repository.outage_freq_distribution(user_level="key", **common)
        sensitive_rows = county_repository.outage_freq_distribution(user_level="sensitive", **common)
    except Exception:
        current_app.logger.exception("Failed to query outage frequency")
        return error("Failed to query outage frequency", 500)

    def build_distribution(rows):
        bucket_map = {r["bucket"]: r["userCount"] for r in rows}
        buckets = [
            {"label": "停电1次", "count": bucket_map.get("1", 0)},
            {"label": "停电2次", "count": bucket_map.get("2", 0)},
            {"label": "停电3次及以上", "count": bucket_map.get("3+", 0)},
        ]
        total = sum(b["count"] for b in buckets)
        for b in buckets:
            b["percentage"] = round(b["count"] / total * 100, 1) if total else 0
        return {"total": total, "distribution": buckets}

    return success({
        "keyUsers": build_distribution(key_rows),
        "sensitiveUsers": build_distribution(sensitive_rows),
    })


@county_bp.route("/equipment-stats", methods=["POST"])
def county_equipment_stats():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    city_id = _optional_str(req_data.get("cityId"))
    county_id = _optional_str(req_data.get("countyId"))
    if city_id and county_id:
        return error("cityId and countyId are mutually exclusive", 400)

    try:
        result = county_repository.equipment_impact_stats(
            begin_time=begin_time,
            end_time=end_time,
            city_id=city_id,
            county_id=county_id,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query equipment stats")
        return error("Failed to query equipment stats", 500)

    return success(result)


@county_bp.route("/equipment-list", methods=["POST"])
def county_equipment_list():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    city_id = _optional_str(req_data.get("cityId"))
    county_id = _optional_str(req_data.get("countyId"))
    if city_id and county_id:
        return error("cityId and countyId are mutually exclusive", 400)

    top = req_data.get("top")
    if top is not None:
        try:
            top = int(top)
            if top < 1:
                return error("top must be greater than 0", 400)
        except (TypeError, ValueError):
            return error("top must be a positive integer", 400)

    try:
        rows = county_repository.equipment_impact_list(
            begin_time=begin_time,
            end_time=end_time,
            city_id=city_id,
            county_id=county_id,
            top=top,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query equipment list")
        return error("Failed to query equipment list", 500)

    return success({"list": rows})


@county_bp.route("/equipment-page", methods=["POST"])
def county_equipment_page():
    req_data = _json_body()
    begin_time, end_time, err = _require_time_range(req_data)
    if err:
        return err

    city_id = _optional_str(req_data.get("cityId"))
    county_id = _optional_str(req_data.get("countyId"))
    if city_id and county_id:
        return error("cityId and countyId are mutually exclusive", 400)

    page, per_page, err = _parse_pagination(req_data)
    if err:
        return err

    try:
        rows, total = county_repository.equipment_impact_page(
            page=page,
            per_page=per_page,
            begin_time=begin_time,
            end_time=end_time,
            city_id=city_id,
            county_id=county_id,
            **_snapshot_filters(req_data),
        )
    except Exception:
        current_app.logger.exception("Failed to query equipment page")
        return error("Failed to query equipment page", 500)

    return success({
        "total": total,
        "page": page,
        "perPage": per_page,
        "list": rows,
    })


@county_bp.route("/equipment-detail", methods=["POST"])
def county_equipment_detail():
    req_data = _json_body()
    equipment_id = _optional_str(req_data.get("equipmentId"))
    if not equipment_id:
        return error("equipmentId is required", 400)

    try:
        result = county_repository.equipment_detail(equipment_id)
    except Exception:
        current_app.logger.exception("Failed to query equipment detail")
        return error("Failed to query equipment detail", 500)

    return success(result)


@county_bp.route("/user-detail", methods=["POST"])
def county_user_detail():
    req_data = _json_body()
    cons_no = _optional_str(req_data.get("consNo"))
    outage_number = _optional_str(req_data.get("outageNumber"))
    if not cons_no or not outage_number:
        return error("consNo and outageNumber are required", 400)

    try:
        result = county_repository.user_outage_detail(cons_no, outage_number)
    except Exception:
        current_app.logger.exception("Failed to query user detail")
        return error("Failed to query user detail", 500)

    return success(result)
