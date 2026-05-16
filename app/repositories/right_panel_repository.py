import re

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

    def overview(
        self,
        begin_time,
        end_time,
        county_id=None,
        city_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        feeder_summary = self.fault_location_by_entity(
            begin_time,
            end_time,
            county_id=county_id,
            entity_type="feeder",
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        substation_summary = self.fault_location_by_entity(
            begin_time,
            end_time,
            county_id=county_id,
            entity_type="substation",
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        return {
            "countyWarnings": self.county_warnings(
                begin_time,
                end_time,
                city_id=city_id,
                snapshot_date=snapshot_date,
                snapshot_start_date=snapshot_start_date,
                snapshot_end_date=snapshot_end_date,
            ),
            "faultLocation": {
                "feeder": feeder_summary,
                "substation": substation_summary,
                "modes": {
                    "feeder": feeder_summary,
                    "substation": substation_summary,
                },
            },
            "outageScope": self.outage_scope_summary(
                begin_time,
                end_time,
                county_id=county_id,
                snapshot_date=snapshot_date,
                snapshot_start_date=snapshot_start_date,
                snapshot_end_date=snapshot_end_date,
            ),
        }

    def county_warnings(
        self,
        begin_time,
        end_time,
        city_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        warning_city_id = city_id or DEFAULT_WARNING_CITY_ID
        rows = self._fetch_all(
            f"""
            SELECT
              c.county_id AS countyId,
              c.county_name AS countyName,
              COUNT(e.outageKey) AS totalEvents,
              SUM(CASE WHEN e.isRestored = 0 THEN 1 ELSE 0 END) AS activeEvents
            FROM county c
            LEFT JOIN ({event_sql}) e ON c.county_id = e.countyId
            WHERE c.city_id = :warning_city_id
            GROUP BY c.county_id, c.county_name, c.id
            ORDER BY c.id
            """,
            {**params, "warning_city_id": warning_city_id},
        )
        return [
            {
                "countyId": row.get("countyId", ""),
                "countyName": row.get("countyName", ""),
                "totalEvents": _to_int(row.get("totalEvents")),
                "activeEvents": _to_int(row.get("activeEvents")),
                "hasOutage": _to_int(row.get("activeEvents")) > 0,
                "level": "danger" if _to_int(row.get("activeEvents")) > 0 else "safe",
            }
            for row in rows
        ]

    def fault_location_by_entity(
        self,
        begin_time,
        end_time,
        county_id=None,
        entity_type="feeder",
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        id_expr, name_expr = self._entity_exprs(entity_type)

        row = self._fetch_one(
            f"""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN affectedUsers > 5000 THEN 1 ELSE 0 END) AS danger,
              SUM(CASE WHEN affectedUsers >= 1000 AND affectedUsers <= 5000 THEN 1 ELSE 0 END) AS warning,
              SUM(CASE WHEN affectedUsers < 1000 THEN 1 ELSE 0 END) AS safe
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
            county_id=county_id,
            dimension=entity_type,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        return _mode_summary(entity_type, row, matched_events=matched_events)

    def fault_summary(
        self,
        begin_time,
        end_time,
        county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        line_summary = self.fault_location_by_entity(
            begin_time=begin_time,
            end_time=end_time,
            county_id=county_id,
            entity_type="line",
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        feeder_summary = {**line_summary, "key": "feeder", "label": "feeder"}
        substation_summary = self.fault_location_by_entity(
            begin_time=begin_time,
            end_time=end_time,
            county_id=county_id,
            entity_type="substation",
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        return {
            "highImpact": {"count": _bar_count(line_summary, "danger")},
            "mediumImpact": {"count": _bar_count(line_summary, "warning")},
            "lowImpact": {"count": _bar_count(line_summary, "safe")},
            "modes": {
                "line": line_summary,
                "feeder": feeder_summary,
                "substation": substation_summary,
            },
        }

    def outage_scope_summary(
        self,
        begin_time,
        end_time,
        county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
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
              SUM(e.affectedEquipment) AS affectedEquipment,
              SUM(e.affectedUsers) AS affectedUsers
            FROM ({event_sql}) e
            """,
            params,
        )
        restored_events = _to_int(row.get("restoredEvents"))
        unrestored_events = _to_int(row.get("unrestoredEvents"))
        affected_equipment = _to_int(row.get("affectedEquipment"))
        affected_users = _to_int(row.get("affectedUsers"))
        return {
            "totalEvents": restored_events + unrestored_events,
            "activeEvents": unrestored_events,
            "totalEquipments": affected_equipment,
            "totalUsers": affected_users,
            "restoredEvents": _to_int(row.get("restoredEvents")),
            "unrestoredEvents": _to_int(row.get("unrestoredEvents")),
            "affectedEquipment": _to_int(row.get("affectedEquipment")),
            "affectedUsers": _to_int(row.get("affectedUsers")),
        }

    def outage_events(
        self,
        begin_time,
        end_time,
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
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        summary = self._event_summary_counts(event_sql, params)

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
            "summary": summary,
            "total": total,
            "page": page,
            "perPage": per_page,
            "list": [self._format_event_row(row) for row in rows],
        }

    def fault_events(
        self,
        begin_time,
        end_time,
        dimension="line",
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
            county_id=county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
        )
        event_sql = self._event_summary_sql(where_sql)
        outer_where, outer_params = self._build_event_outer_filter(
            keyword=keyword,
            outage_nature=outage_nature,
            dimension=dimension,
        )
        filtered_event_sql = f"SELECT * FROM ({event_sql}) e {outer_where}"
        merged_params = {**params, **outer_params}
        summary = self._event_summary_counts(filtered_event_sql, merged_params)

        count_row = self._fetch_one(
            f"SELECT COUNT(*) AS total FROM ({filtered_event_sql}) fe",
            merged_params,
        )
        total = _to_int(count_row.get("total"))

        rows = self._fetch_all(
            f"""
            SELECT *
            FROM ({filtered_event_sql}) fe
            ORDER BY fe.beginTime DESC, fe.outageNumber DESC
            LIMIT :_limit OFFSET :_offset
            """,
            {
                **merged_params,
                "_limit": per_page,
                "_offset": (page - 1) * per_page,
            },
        )
        return {
            "summary": summary,
            "total": total,
            "page": page,
            "perPage": per_page,
            "dimension": _normalize_dimension(dimension),
            "list": [self._format_event_row(row) for row in rows],
        }

    def fault_event_match_count(
        self,
        begin_time,
        end_time,
        county_id=None,
        dimension="line",
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_sql, params = self._build_base_where(
            begin_time,
            end_time,
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

    def outage_event_detail(self, outage_number):
        where_sql = """
        WHERE (
          ou.outage_number = :outage_number
          OR ou.record_key = :outage_number
        )
        """
        event_sql = self._event_summary_sql(where_sql)
        row = self._fetch_one(
            f"SELECT * FROM ({event_sql}) e LIMIT 1",
            {"outage_number": outage_number},
        )
        if not row:
            return {}

        detail = self._format_event_row(row)
        detail.update({
            "feederName": row.get("feederName") or "",
            "substationName": row.get("substationName") or "",
            "maintGroupName": row.get("maintGroupName") or "",
            "equipmentName": row.get("equipmentName") or "",
            "keyUserCount": _to_int(row.get("keyUserCount")),
            "sensitiveUserCount": _to_int(row.get("sensitiveUserCount")),
            "normalUserCount": _to_int(row.get("normalUserCount")),
        })
        return detail

    def outage_chains(
        self,
        begin_time,
        end_time,
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
              MAX(IFNULL(f.feeder_name, '')) AS feederName,
              GROUP_CONCAT(DISTINCT NULLIF(f.feeder_id, '') ORDER BY f.feeder_id SEPARATOR '|') AS feederIdsText,
              GROUP_CONCAT(DISTINCT NULLIF(f.feeder_name, '') ORDER BY f.feeder_name SEPARATOR '|') AS feederNamesText,
              MAX(IFNULL(s.subs_name, '')) AS substationName,
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
            "list": [self._format_chain_row(row) for row in rows],
        }

    def _build_base_where(
        self,
        begin_time,
        end_time,
        county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        parts = [
            "ou.`begin_time` >= :begin_time",
            "ou.`begin_time` <= :end_time",
        ]
        params = {
            "begin_time": begin_time,
            "end_time": end_time,
        }
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
          CASE WHEN MAX(NULLIF(ou.end_time, '')) IS NULL THEN 0 ELSE 1 END AS isRestored,
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

    def _chain_summary_sql(self, where_sql):
        event_key = self._event_key_expr()
        return f"""
        SELECT
          {event_key} AS outageKey,
          COALESCE(MAX(NULLIF(ou.outage_number, '')), MAX({event_key})) AS outageNumber,
          MAX(COALESCE(c.county_name, ou.rdt_county_name, '')) AS countyName,
          MIN(NULLIF(ou.begin_time, '')) AS beginTime,
          MAX(IFNULL(f.feeder_name, '')) AS feederName,
          GROUP_CONCAT(DISTINCT NULLIF(f.feeder_id, '') ORDER BY f.feeder_id SEPARATOR '|') AS feederIdsText,
          GROUP_CONCAT(DISTINCT NULLIF(f.feeder_name, '') ORDER BY f.feeder_name SEPARATOR '|') AS feederNamesText,
          MAX(IFNULL(s.subs_name, '')) AS substationName,
          MAX(COALESCE(ou.rdt_maint_group_name, '')) AS maintGroupName,
          GROUP_CONCAT(DISTINCT NULLIF(ou.equipment_id, '') ORDER BY ou.equipment_id SEPARATOR '|') AS equipmentIdsText,
          GROUP_CONCAT(
            DISTINCT NULLIF(ou.equipment_name, '')
            ORDER BY ou.equipment_name
            SEPARATOR '|'
          ) AS equipmentNamesText,
          GROUP_CONCAT(DISTINCT CASE
            WHEN ou.is_key_user = 1 THEN NULLIF(ou.cons_name, '')
          END ORDER BY ou.cons_name SEPARATOR '|') AS importantUserText,
          GROUP_CONCAT(DISTINCT CASE
            WHEN ou.is_sensitive_user = 1 THEN NULLIF(ou.cons_name, '')
          END ORDER BY ou.cons_name SEPARATOR '|') AS sensitiveUserText,
          COUNT(DISTINCT CASE
            WHEN ou.is_key_user = 0 AND ou.is_sensitive_user = 0 THEN NULLIF(ou.cons_no, '')
          END) AS normalUserCount
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
        return {
            "totalEvents": _to_int(row.get("totalEvents")),
            "plannedEvents": _to_int(row.get("plannedEvents")),
            "faultEvents": _to_int(row.get("faultEvents")),
            "otherEvents": _to_int(row.get("otherEvents")),
            "restoredEvents": _to_int(row.get("restoredEvents")),
            "unrestoredEvents": _to_int(row.get("unrestoredEvents")),
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
        feeder_ids = _split_user_text(row.get("feederIdsText"))
        feeder_names = _split_user_text(row.get("feederNamesText"))
        equipment_ids = _split_user_text(row.get("equipmentIdsText"))
        equipment_names = _split_user_text(row.get("equipmentNamesText"))
        match_status = "equipment_feeder_matched" if feeder_ids or feeder_names else "equipment_only"
        return {
            "outageNumber": row.get("outageNumber", ""),
            "countyId": row.get("countyId", ""),
            "countyName": row.get("countyName", ""),
            "affectedUsers": _to_int(row.get("affectedUsers")),
            "affectedEquipment": _to_int(row.get("affectedEquipment")),
            "outageNature": _nature_text(nature_code),
            "outageNatureCode": nature_code,
            "isRestored": is_restored,
            "status": "restored" if is_restored else "repairing",
            "outageFlag": "1" if is_restored else "0",
            "beginTime": row.get("beginTime") or "",
            "endTime": row.get("endTime") or None,
            "feederId": row.get("feederId", ""),
            "feederName": row.get("feederName", ""),
            "rdtFeederName": row.get("feederName", ""),
            "feederIds": feeder_ids,
            "feederNames": feeder_names,
            "substationId": row.get("substationId", ""),
            "substationName": row.get("substationName", ""),
            "rdtSubsName": row.get("substationName", ""),
            "maintGroupId": row.get("maintGroupId", ""),
            "maintGroupName": row.get("maintGroupName", ""),
            "equipmentName": row.get("equipmentName", ""),
            "equipmentIds": equipment_ids,
            "equipmentNames": equipment_names,
            "matchStatus": match_status,
        }

    def _format_chain_row(self, row):
        important_users = _split_user_text(row.get("importantUserText"))
        sensitive_users = _split_user_text(row.get("sensitiveUserText"))
        feeder_ids = _split_user_text(row.get("feederIdsText"))
        feeder_names = _split_user_text(row.get("feederNamesText"))
        equipment_ids = _split_user_text(row.get("equipmentIdsText"))
        equipment_names = _split_user_text(row.get("equipmentNamesText"))
        outage_number = row.get("outageNumber", "")
        feeder_name = row.get("feederName") or "-"
        substation_name = row.get("substationName") or "-"
        return {
            "key": outage_number,
            "outageNumber": outage_number,
            "countyName": row.get("countyName", ""),
            "feederName": feeder_name,
            "rdtFeederName": feeder_name,
            "feederIds": feeder_ids,
            "feederNames": feeder_names,
            "substationName": substation_name,
            "rdtSubsName": substation_name,
            "maintGroupName": row.get("maintGroupName") or "-",
            "equipmentIds": equipment_ids,
            "equipmentNames": equipment_names,
            "importantUsers": important_users,
            "sensitiveUsers": sensitive_users,
            "importantUserText": ", ".join(important_users) if important_users else "none",
            "sensitiveUserText": ", ".join(sensitive_users) if sensitive_users else "none",
            "normalUserCount": _to_int(row.get("normalUserCount")),
            "matchStatus": "equipment_feeder_matched" if feeder_ids or feeder_names else "equipment_only",
        }


def _to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bar_count(summary, key):
    bars = summary.get("bars") if isinstance(summary, dict) else []
    for item in bars:
        if item.get("key") == key or item.get("riskKey") == key:
            return _to_int(item.get("count"))
    return 0


def _mode_summary(key, row, matched_events=0):
    display_key = str(key or "").strip().lower()
    normalized = _normalize_dimension(display_key) or display_key
    labels = {
        "line": "line",
        "feeder": "feeder",
        "substation": "substation",
        "equipment": "equipment",
    }
    danger = _to_int(row.get("danger"))
    warning = _to_int(row.get("warning"))
    safe = _to_int(row.get("safe"))
    total = _to_int(row.get("total"))
    bars = [
        {
            "level": "danger",
            "key": "danger",
            "riskKey": "danger",
            "colorKey": "red",
            "colorLabel": "red",
            "colorClass": "red",
            "count": danger,
        },
        {
            "level": "warning",
            "key": "warning",
            "riskKey": "warning",
            "colorKey": "yellow",
            "colorLabel": "yellow",
            "colorClass": "yellow",
            "count": warning,
        },
        {
            "level": "safe",
            "key": "safe",
            "riskKey": "safe",
            "colorKey": "green",
            "colorLabel": "green",
            "colorClass": "green",
            "count": safe,
        },
    ]
    return {
        "key": display_key or normalized,
        "dimension": normalized,
        "label": labels.get(display_key, labels.get(normalized, normalized)),
        "total": total,
        "matchedEvents": _to_int(matched_events),
        "bars": bars,
        "colorBars": [
            {"key": item["colorKey"], "riskKey": item["riskKey"], "count": item["count"]}
            for item in bars
        ],
    }


def _nature_text(value):
    plain = str(value or "").strip()
    if plain == "01":
        return "planned"
    if plain == "02":
        return "fault"
    return "other"


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
