import re
from datetime import datetime

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_PLACEHOLDER_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")

_POOL_DEFAULTS = {
    "mincached": 0,
    "maxcached": 8,
    "maxconnections": 20,
}

DEFAULT_WARNING_CITY_ID = "1100F3DE22316FADE050007F01006CBE"


class RightPanelRepository:
    def __init__(self, app=None):
        self.user_score_table = "outage_user_full"
        self._pool = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        table_name = app.config.get("MYSQL_USER_SCORE_TABLE", "outage_user_full")
        if not _TABLE_NAME_RE.fullmatch(table_name):
            raise ValueError(
                "MYSQL_USER_SCORE_TABLE must contain only letters, numbers, and underscores"
            )
        self.user_score_table = table_name
        self._pool = PooledDB(
            creator=pymysql,
            cursorclass=DictCursor,
            autocommit=True,
            host=app.config.get("MYSQL_HOST", "127.0.0.1"),
            port=int(app.config.get("MYSQL_PORT", 3306)),
            user=app.config.get("MYSQL_USER", "root"),
            passwd=app.config.get("MYSQL_PASSWORD", ""),
            db=app.config.get("MYSQL_DATABASE", "tangshan_backend"),
            charset=app.config.get("MYSQL_CHARSET", "utf8mb4"),
            **_POOL_DEFAULTS,
        )

    def _connect(self):
        if not self._pool:
            raise RuntimeError("RightPanelRepository.init_app must be called before use")
        return self._pool.connection()

    def _prepare_sql(self, sql):
        return _PLACEHOLDER_RE.sub(r"%(\1)s", sql)

    def _fetch_all(self, sql, params=None):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(self._prepare_sql(sql), params or {})
                return list(cur.fetchall())
        finally:
            conn.close()

    def _fetch_one(self, sql, params=None):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(self._prepare_sql(sql), params or {})
                row = cur.fetchone()
                return dict(row) if row else {}
        finally:
            conn.close()

    def county_outage_status(
        self,
        begin_time,
        end_time,
        city_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        join_parts = []
        params = {}
        if begin_time and end_time:
            join_parts.append(
                "(ou.`begin_time` <= :filter_end_time AND "
                "COALESCE(NULLIF(CAST(ou.`end_time` AS CHAR), ''), "
                "'9999-12-31 23:59:59') >= :filter_begin_time)"
            )
            params["filter_begin_time"] = begin_time
            params["filter_end_time"] = end_time
        elif begin_time:
            join_parts.append(
                "COALESCE(NULLIF(CAST(ou.`end_time` AS CHAR), ''), "
                "'9999-12-31 23:59:59') >= :filter_begin_time"
            )
            params["filter_begin_time"] = begin_time
        elif end_time:
            join_parts.append("ou.`begin_time` <= :filter_end_time")
            params["filter_end_time"] = end_time
        if snapshot_date:
            join_parts.append("ou.snapshot_date = :snapshot_date")
            params["snapshot_date"] = snapshot_date
        else:
            if snapshot_start_date:
                join_parts.append("ou.snapshot_date >= :snapshot_start_date")
                params["snapshot_start_date"] = snapshot_start_date
            if snapshot_end_date:
                join_parts.append("ou.snapshot_date <= :snapshot_end_date")
                params["snapshot_end_date"] = snapshot_end_date

        join_sql = " AND ".join(join_parts)
        warning_city_id = city_id or DEFAULT_WARNING_CITY_ID

        rows = self._fetch_all(
            f"""
            SELECT
              c.county_name AS countyName,
              CASE WHEN COUNT(ou.id) > 0 THEN 1 ELSE 0 END AS hasOutage
            FROM county c
            LEFT JOIN `{self.user_score_table}` ou
              ON c.county_id = ou.rdt_county_id
              AND {join_sql}
            WHERE c.city_id = :warning_city_id
            GROUP BY c.county_id, c.county_name, c.id
            ORDER BY c.id
            """,
            {**params, "warning_city_id": warning_city_id},
        )
        return [
            {
                "countyName": row.get("countyName", ""),
                "hasOutage": bool(row.get("hasOutage")),
            }
            for row in rows
        ]

    def fault_location_summary(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        dimension="feeder",
        danger_threshold=5000,
        warning_threshold=1000,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        id_expr, name_expr = self._entity_exprs(dimension)
        params["danger_threshold"] = danger_threshold
        params["warning_threshold"] = warning_threshold

        row = self._fetch_one(
            f"""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN affectedUsers > :danger_threshold THEN 1 ELSE 0 END) AS danger,
              SUM(CASE WHEN affectedUsers >= :warning_threshold AND affectedUsers <= :danger_threshold THEN 1 ELSE 0 END) AS warning,
              SUM(CASE WHEN affectedUsers < :warning_threshold THEN 1 ELSE 0 END) AS safe
            FROM (
              SELECT
                {id_expr} AS entityId,
                {name_expr} AS entityName,
                COUNT(DISTINCT NULLIF(ou.cons_no, '')) AS affectedUsers
              {self._joined_from_sql()}
              {where_sql}
                AND {id_expr} IS NOT NULL
                AND {id_expr} <> ''
              GROUP BY {id_expr}, {name_expr}
            ) t
            """,
            params,
        )
        matched_events = self.fault_event_match_count(
            begin_time=begin_time,
            end_time=end_time,
            city_id=city_id,
            county_id=county_id,
            dimension=dimension,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        return {
            "total": _to_int(row.get("total")),
            "matchedEvents": _to_int(matched_events),
            "danger": _to_int(row.get("danger")),
            "warning": _to_int(row.get("warning")),
            "safe": _to_int(row.get("safe")),
        }

    def outage_scope(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        row = self._fetch_one(
            f"""
            SELECT
              SUM(CASE WHEN e.isRestored = 1 THEN 1 ELSE 0 END) AS restoredEvents,
              SUM(CASE WHEN e.isRestored = 0 THEN 1 ELSE 0 END) AS unrestoredEvents,
              SUM(e.affectedUsers) AS affectedUsersSum,
              SUM(e.affectedEquipment) AS affectedEquipmentSum
            FROM ({event_sql}) e
            """,
            params,
        )
        restored = _to_int(row.get("restoredEvents"))
        unrestored = _to_int(row.get("unrestoredEvents"))

        event_key = self._event_key_expr()
        stats = self._fetch_one(
            f"""
            SELECT
              COUNT(DISTINCT NULLIF(ou.cons_no, '')) AS affectedUsers,
              COUNT(DISTINCT NULLIF(ou.equipment_id, '')) AS affectedEquipment
            {self._joined_from_sql()}
            {where_sql}
            """,
            params,
        )
        return {
            "totalEvents": restored + unrestored,
            "restoredEvents": restored,
            "unrestoredEvents": unrestored,
            "affectedEquipment": _to_int(stats.get("affectedEquipment")),
            "affectedUsers": _to_int(stats.get("affectedUsers")),
        }

    def outage_events_summary(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        keyword=None,
        outage_nature=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        return self._event_summary_counts(event_sql, params)

    def outage_events_list(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        keyword=None,
        outage_nature=None,
        page=1,
        per_page=20,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)

        outer_where, outer_params = self._build_event_outer_filter(keyword, outage_nature)
        count_row = self._fetch_one(
            f"SELECT COUNT(*) AS total FROM ({event_sql}) e {outer_where}",
            {**params, **outer_params},
        )
        total = _to_int(count_row.get("total"))

        rows = self._fetch_all(
            f"""
            SELECT *
            FROM ({event_sql}) e
            {outer_where}
            ORDER BY e.beginTime DESC, e.outageNumber DESC
            LIMIT :_limit OFFSET :_offset
            """,
            {
                **params,
                **outer_params,
                "_limit": per_page,
                "_offset": (page - 1) * per_page,
            },
        )
        return {
            "total": total,
            "page": page,
            "perPage": per_page,
            "list": [self._format_event_row_brief(row) for row in rows],
        }

    def fault_event_match_count(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        dimension="line",
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        dimension_where = self._dimension_outer_filter_sql(dimension)
        row = self._fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM ({event_sql}) e
            WHERE {dimension_where}
            """,
            params,
        )
        return _to_int(row.get("total"))

    def outage_event_detail_feeder(self, outage_number):
        where_sql = """
        WHERE (
          ou.outage_number = :outage_number
          OR ou.record_key = :outage_number
        )
        """
        event_sql = self._event_summary_sql(where_sql)
        row = self._fetch_one(
            f"SELECT * FROM ({event_sql}) e LIMIT 1",
            {"outage_number": outage_number, "filter_end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        )
        if not row:
            return {}

        detail = self._format_event_row(row)
        feeder_ids = [x for x in (row.get("feederIdsText") or "").split("|") if x]
        feeder_names = [x for x in (row.get("feederNamesText") or "").split("|") if x]
        detail.update({
            "feederId": feeder_ids[0] if len(feeder_ids) == 1 else feeder_ids,
            "feederName": feeder_names[0] if len(feeder_names) == 1 else feeder_names,
            "keyUserCount": _to_int(row.get("keyUserCount")),
            "sensitiveUserCount": _to_int(row.get("sensitiveUserCount")),
            "normalUserCount": _to_int(row.get("normalUserCount")),
        })
        return detail

    def outage_event_detail_substation(self, outage_number):
        where_sql = """
        WHERE (
          ou.outage_number = :outage_number
          OR ou.record_key = :outage_number
        )
        """
        event_sql = self._event_summary_sql(where_sql)
        row = self._fetch_one(
            f"SELECT * FROM ({event_sql}) e LIMIT 1",
            {"outage_number": outage_number, "filter_end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        )
        if not row:
            return {}

        detail = self._format_event_row(row)
        substation_ids = [x for x in (row.get("substationIdsText") or "").split("|") if x]
        substation_names = [x for x in (row.get("substationNamesText") or "").split("|") if x]
        detail.update({
            "substationId": substation_ids[0] if len(substation_ids) == 1 else substation_ids,
            "substationName": substation_names[0] if len(substation_names) == 1 else substation_names,
            "keyUserCount": _to_int(row.get("keyUserCount")),
            "sensitiveUserCount": _to_int(row.get("sensitiveUserCount")),
            "normalUserCount": _to_int(row.get("normalUserCount")),
        })
        return detail

    def outage_chains(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        page=1,
        per_page=20,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            city_id=city_id,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_key = self._event_key_expr()
        count_row = self._fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM (
              SELECT {event_key} AS outageKey
              FROM `{self.user_score_table}` ou
              {where_sql}
              GROUP BY {event_key}
            ) c
            """,
            params,
        )
        total = _to_int(count_row.get("total"))
        page_key_sql = f"""
        SELECT
          {event_key} AS outageKey,
          MIN(NULLIF(ou.begin_time, '')) AS beginTime,
          COALESCE(MAX(NULLIF(ou.outage_number, '')), MAX({event_key})) AS outageNumber
        FROM `{self.user_score_table}` ou
        {where_sql}
        GROUP BY {event_key}
        ORDER BY beginTime DESC, outageNumber DESC
        LIMIT :_limit OFFSET :_offset
        """
        rows = self._fetch_all(
            f"""
            SELECT
              pk.outageKey,
              pk.outageNumber,
              MAX(COALESCE(c.county_name, ou.rdt_county_name, '')) AS countyName,
              pk.beginTime,
              GROUP_CONCAT(DISTINCT NULLIF(f.feeder_id, '') ORDER BY f.feeder_id SEPARATOR '|') AS feederIdsText,
              GROUP_CONCAT(DISTINCT NULLIF(f.feeder_name, '') ORDER BY f.feeder_name SEPARATOR '|') AS feederNamesText,
              GROUP_CONCAT(DISTINCT NULLIF(s.subs_id, '') ORDER BY s.subs_id SEPARATOR '|') AS substationIdsText,
              GROUP_CONCAT(DISTINCT NULLIF(s.subs_name, '') ORDER BY s.subs_name SEPARATOR '|') AS substationNamesText,
              MAX(COALESCE(ou.rdt_maint_group_name, '')) AS maintGroupName,
              GROUP_CONCAT(DISTINCT NULLIF(ou.equipment_id, '') ORDER BY ou.equipment_id SEPARATOR '|') AS equipmentIdsText,
              GROUP_CONCAT(DISTINCT NULLIF(ou.equipment_name, '') ORDER BY ou.equipment_name SEPARATOR '|') AS equipmentNamesText,
              GROUP_CONCAT(DISTINCT CASE
                WHEN ou.is_key_user = 1 THEN NULLIF(ou.cons_name, '')
              END ORDER BY ou.cons_name SEPARATOR '|') AS importantUserText,
              GROUP_CONCAT(DISTINCT CASE
                WHEN ou.is_sensitive_user = 1 THEN NULLIF(ou.cons_name, '')
              END ORDER BY ou.cons_name SEPARATOR '|') AS sensitiveUserText,
              COUNT(DISTINCT CASE
                WHEN ou.is_key_user = 0 AND ou.is_sensitive_user = 0 THEN NULLIF(ou.cons_no, '')
              END) AS normalUserCount
            FROM ({page_key_sql}) pk
            JOIN `{self.user_score_table}` ou
              ON {event_key} = pk.outageKey
            LEFT JOIN equipment_feeder ef ON ou.equipment_id = ef.equipment_id
            LEFT JOIN feeder f ON ef.feeder_id = f.feeder_id
            LEFT JOIN substation s ON f.subs_id = s.subs_id
            LEFT JOIN county c ON ou.rdt_county_id = c.county_id
            GROUP BY pk.outageKey, pk.outageNumber, pk.beginTime
            ORDER BY pk.beginTime DESC, pk.outageNumber DESC
            """,
            {
                **params,
                "_limit": per_page,
                "_offset": (page - 1) * per_page,
            },
        )
        return {
            "total": total,
            "page": page,
            "perPage": per_page,
            "list": [self._format_chain_row_brief(row) for row in rows],
        }

    def _build_base_where(
        self,
        begin_time,
        end_time,
        city_id=None,
        county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        parts = []
        params = {}
        if begin_time and end_time:
            parts.append(
                "(ou.`begin_time` <= :filter_end_time AND "
                "COALESCE(NULLIF(CAST(ou.`end_time` AS CHAR), ''), "
                "'9999-12-31 23:59:59') >= :filter_begin_time)"
            )
            params["filter_begin_time"] = begin_time
            params["filter_end_time"] = end_time
        elif begin_time:
            parts.append(
                "COALESCE(NULLIF(CAST(ou.`end_time` AS CHAR), ''), "
                "'9999-12-31 23:59:59') >= :filter_begin_time"
            )
            params["filter_begin_time"] = begin_time
        elif end_time:
            parts.append("ou.`begin_time` <= :filter_end_time")
            params["filter_end_time"] = end_time
        if not city_id and not county_id:
            city_id = DEFAULT_WARNING_CITY_ID
        if city_id:
            parts.append("ou.rdt_city_id = :city_id")
            params["city_id"] = city_id
        if county_id:
            parts.append("ou.rdt_county_id = :county_id")
            params["county_id"] = county_id
        if snapshot_date:
            parts.append("ou.snapshot_date = :snapshot_date")
            params["snapshot_date"] = snapshot_date
        else:
            if snapshot_start_date:
                parts.append("ou.snapshot_date >= :snapshot_start_date")
                params["snapshot_start_date"] = snapshot_start_date
            if snapshot_end_date:
                parts.append("ou.snapshot_date <= :snapshot_end_date")
                params["snapshot_end_date"] = snapshot_end_date
        return "WHERE " + " AND ".join(parts), params

    def _joined_from_sql(self):
        return f"""
        FROM `{self.user_score_table}` ou
        LEFT JOIN equipment_feeder ef ON ou.equipment_id = ef.equipment_id
        LEFT JOIN feeder f ON ef.feeder_id = f.feeder_id
        LEFT JOIN substation s ON f.subs_id = s.subs_id
        LEFT JOIN county c ON ou.rdt_county_id = c.county_id
        """

    def _event_summary_sql(self, where_sql):
        event_key = self._event_key_expr()
        return f"""
        SELECT
          {event_key} AS outageKey,
          COALESCE(MAX(NULLIF(ou.outage_number, '')), MAX({event_key})) AS outageNumber,
          MAX(COALESCE(c.county_id, ou.rdt_county_id, '')) AS countyId,
          MAX(COALESCE(c.county_name, ou.rdt_county_name, '')) AS countyName,
          MIN(NULLIF(ou.begin_time, '')) AS beginTime,
          MAX(NULLIF(ou.end_time, '')) AS endTime,
          MAX(IFNULL(ou.outage_nature, '')) AS outageNatureCode,
          MIN(CASE WHEN ou.end_time IS NOT NULL AND ou.end_time != '' AND ou.end_time <= :filter_end_time THEN 1 ELSE 0 END) AS isRestored,
          COUNT(DISTINCT NULLIF(ou.cons_no, '')) AS affectedUsers,
          COUNT(DISTINCT NULLIF(ou.equipment_id, '')) AS affectedEquipment,
          COUNT(DISTINCT CASE WHEN ou.is_key_user = 1 THEN NULLIF(ou.cons_no, '') END) AS keyUserCount,
          COUNT(DISTINCT CASE WHEN ou.is_sensitive_user = 1 THEN NULLIF(ou.cons_no, '') END) AS sensitiveUserCount,
          COUNT(DISTINCT CASE
            WHEN ou.is_key_user = 0 AND ou.is_sensitive_user = 0 THEN NULLIF(ou.cons_no, '')
          END) AS normalUserCount,
          MAX(IFNULL(f.feeder_id, '')) AS feederId,
          MAX(IFNULL(f.feeder_name, '')) AS feederName,
          GROUP_CONCAT(DISTINCT NULLIF(f.feeder_id, '') ORDER BY f.feeder_id SEPARATOR '|') AS feederIdsText,
          GROUP_CONCAT(DISTINCT NULLIF(f.feeder_name, '') ORDER BY f.feeder_name SEPARATOR '|') AS feederNamesText,
          MAX(IFNULL(s.subs_id, '')) AS substationId,
          MAX(IFNULL(s.subs_name, '')) AS substationName,
          GROUP_CONCAT(DISTINCT NULLIF(s.subs_id, '') ORDER BY s.subs_id SEPARATOR '|') AS substationIdsText,
          GROUP_CONCAT(DISTINCT NULLIF(s.subs_name, '') ORDER BY s.subs_name SEPARATOR '|') AS substationNamesText,
          MAX(COALESCE(ou.rdt_maint_group_id, '')) AS maintGroupId,
          MAX(COALESCE(ou.rdt_maint_group_name, '')) AS maintGroupName,
          MAX(COALESCE(NULLIF(ou.equipment_name, ''), '')) AS equipmentName,
          GROUP_CONCAT(DISTINCT NULLIF(ou.equipment_id, '') ORDER BY ou.equipment_id SEPARATOR '|') AS equipmentIdsText,
          GROUP_CONCAT(
            DISTINCT NULLIF(ou.equipment_name, '')
            ORDER BY ou.equipment_name
            SEPARATOR '|'
          ) AS equipmentNamesText
        {self._joined_from_sql()}
        {where_sql}
        GROUP BY {event_key}
        """

    @staticmethod
    def _event_key_expr():
        return "COALESCE(NULLIF(ou.outage_number, ''), ou.record_key, CAST(ou.id AS CHAR))"

    def _event_summary_counts(self, event_sql, params):
        row = self._fetch_one(
            f"""
            SELECT
              COUNT(*) AS totalEvents,
              SUM(CASE WHEN {self._nature_bucket_sql('e.outageNatureCode')} = 'planned' THEN 1 ELSE 0 END) AS plannedEvents,
              SUM(CASE WHEN {self._nature_bucket_sql('e.outageNatureCode')} = 'fault' THEN 1 ELSE 0 END) AS faultEvents,
              SUM(CASE WHEN {self._nature_bucket_sql('e.outageNatureCode')} = 'other' THEN 1 ELSE 0 END) AS otherEvents,
              SUM(CASE WHEN e.isRestored = 1 THEN 1 ELSE 0 END) AS restoredEvents,
              SUM(CASE WHEN e.isRestored = 0 THEN 1 ELSE 0 END) AS unrestoredEvents
            FROM ({event_sql}) e
            """,
            params,
        )
        total = _to_int(row.get("totalEvents"))
        planned = _to_int(row.get("plannedEvents"))
        fault = _to_int(row.get("faultEvents"))
        other = _to_int(row.get("otherEvents"))
        restored = _to_int(row.get("restoredEvents"))
        unrestored = _to_int(row.get("unrestoredEvents"))

        def _pct(value):
            return round(value / total * 100, 2) if total > 0 else 0.0

        return {
            "totalEvents": total,
            "natureRatio": [
                {"code": "01", "value": planned, "percent": _pct(planned)},
                {"code": "02", "value": fault, "percent": _pct(fault)},
                {"code": "03", "value": other, "percent": _pct(other)},
            ],
            "restoredEvents": restored,
            "unrestoredEvents": unrestored,
            "restoredRate": _pct(restored),
        }

    def _build_event_outer_filter(self, keyword=None, outage_nature=None, dimension=None):
        parts = []
        params = {}
        if keyword:
            parts.append("(e.outageNumber LIKE :keyword OR e.countyName LIKE :keyword)")
            params["keyword"] = f"%{keyword}%"

        nature_bucket = _normalize_nature_bucket(outage_nature)
        if nature_bucket:
            parts.append(f"{self._nature_bucket_sql('e.outageNatureCode')} = :nature_bucket")
            params["nature_bucket"] = nature_bucket

        dimension_sql = self._dimension_outer_filter_sql(dimension)
        if dimension_sql:
            parts.append(dimension_sql)

        if not parts:
            return "", params
        return "WHERE " + " AND ".join(parts), params

    @staticmethod
    def _entity_exprs(entity_type):
        dimension = _normalize_dimension(entity_type)
        if dimension == "substation":
            return "s.subs_id", "s.subs_name"
        if dimension == "equipment":
            return "ou.equipment_id", "ou.equipment_name"
        return "f.feeder_id", "f.feeder_name"

    @staticmethod
    def _dimension_outer_filter_sql(dimension=None):
        normalized = _normalize_dimension(dimension)
        if normalized == "substation":
            return "((e.substationId IS NOT NULL AND e.substationId <> '') OR (e.substationName IS NOT NULL AND e.substationName <> ''))"
        if normalized == "equipment":
            return "((e.equipmentName IS NOT NULL AND e.equipmentName <> '') OR e.affectedEquipment > 0)"
        if normalized == "line":
            return "((e.feederId IS NOT NULL AND e.feederId <> '') OR (e.feederName IS NOT NULL AND e.feederName <> ''))"
        return ""

    @staticmethod
    def _nature_bucket_sql(column):
        return f"""
        CASE
          WHEN {column} = '01' THEN 'planned'
          WHEN {column} = '02' THEN 'fault'
          ELSE 'other'
        END
        """

    def _format_event_row(self, row):
        nature_code = str(row.get("outageNatureCode") or "").strip()
        is_restored = _to_int(row.get("isRestored")) == 1
        feeder_names = _split_user_text(row.get("feederNamesText"))
        equipment_names = _split_user_text(row.get("equipmentNamesText"))
        match_status = "equipment_feeder_matched" if feeder_names else "equipment_only"
        return {
            "outageNumber": row.get("outageNumber", ""),
            "countyName": row.get("countyName", ""),
            "affectedUsers": _to_int(row.get("affectedUsers")),
            "affectedEquipment": _to_int(row.get("affectedEquipment")),
            "outageNature": nature_code or "03",
            "isRestored": is_restored,
            "beginTime": row.get("beginTime") or "",
            "endTime": row.get("endTime") or None,
            "equipmentNames": equipment_names,
            "matchStatus": match_status,
        }

    @staticmethod
    def _format_event_row_brief(row):
        nature_code = str(row.get("outageNatureCode") or "").strip()
        return {
            "outageNumber": row.get("outageNumber", ""),
            "countyName": row.get("countyName", ""),
            "affectedUsers": _to_int(row.get("affectedUsers")),
            "outageNature": nature_code or "03",
        }

    @staticmethod
    def _format_chain_row_brief(row):
        important_users = _split_user_text(row.get("importantUserText"))
        sensitive_users = _split_user_text(row.get("sensitiveUserText"))
        outage_number = row.get("outageNumber", "")
        feeder_ids = [x for x in (row.get("feederIdsText") or "").split("|") if x]
        feeder_names = [x for x in (row.get("feederNamesText") or "").split("|") if x]
        substation_ids = [x for x in (row.get("substationIdsText") or "").split("|") if x]
        substation_names = [x for x in (row.get("substationNamesText") or "").split("|") if x]
        return {
            "outageNumber": outage_number,
            "feederId": feeder_ids[0] if len(feeder_ids) == 1 else feeder_ids,
            "feederName": feeder_names[0] if len(feeder_names) == 1 else feeder_names,
            "substationId": substation_ids[0] if len(substation_ids) == 1 else substation_ids,
            "substationName": substation_names[0] if len(substation_names) == 1 else substation_names,
            "importantUserCount": len(important_users),
            "importantUsers": important_users,
            "sensitiveUserCount": len(sensitive_users),
            "sensitiveUsers": sensitive_users,
            "normalUserCount": _to_int(row.get("normalUserCount")),
        }


def _to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_nature_bucket(value):
    plain = str(value or "").strip().lower()
    if not plain:
        return None
    if plain in ("planned", "plan", "01"):
        return "planned"
    if plain in ("fault", "02"):
        return "fault"
    if plain in ("other", "03"):
        return "other"
    return None


def _normalize_dimension(value):
    plain = str(value or "").strip().lower()
    if plain in ("line", "feeder", "circuit"):
        return "line"
    if plain in ("substation", "subs", "station"):
        return "substation"
    if plain in ("equipment", "equip", "device"):
        return "equipment"
    return ""


def _split_user_text(value):
    text = str(value or "").strip()
    if not text:
        return []
    return [item for item in text.split("|") if item]


right_panel_repository = RightPanelRepository()
