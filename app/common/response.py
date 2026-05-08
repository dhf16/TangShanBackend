from datetime import datetime, timedelta, timezone

from flask import jsonify

_CN_TZ = timezone(timedelta(hours=8))


def success(data=None, http_status=200):
    return jsonify({
        "code": 0,
        "success": True,
        "message": "ok",
        "data": data,
        "timestamp": datetime.now(_CN_TZ).isoformat(),
    }), http_status


def error(message, code=400, detail=None):
    error_item = {"message": message, "code": code}
    if detail is not None:
        error_item["detail"] = detail

    return jsonify({
        "code": code,
        "success": False,
        "message": message,
        "data": None,
        "errors": [error_item],
        "timestamp": datetime.now(_CN_TZ).isoformat(),
    }), code
