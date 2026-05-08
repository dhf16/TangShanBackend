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


class CountyRepository:
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
            raise RuntimeError("CountyRepository.init_app must be called before use")
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

    def list_counties(self, city_id=None):
        if city_id:
            sql = (
                "SELECT county_id, county_name, city_id "
                "FROM county WHERE city_id = :city_id ORDER BY id"
            )
            params = {"city_id": city_id}
        else:
            sql = "SELECT county_id, county_name, city_id FROM county ORDER BY id"
            params = {}

        rows = self._fetch_all(sql, params)
        for row in rows:
            row["cityId"] = row.pop("city_id")
            row["countyId"] = row.pop("county_id")
            row["countyName"] = row.pop("county_name")
        return rows

    def stats_by_county(
        self,
        begin_time=None,
        end_time=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_parts, params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        sql = f"""
        SELECT
          IFNULL(rdt_county_id, '') AS countyId,
          IFNULL(rdt_county_name, '') AS countyName,
          COUNT(*) AS totalUsers,
          SUM(CASE WHEN is_key_user = 1 THEN 1 ELSE 0 END) AS keyUsers,
          SUM(CASE WHEN is_sensitive_user = 1 THEN 1 ELSE 0 END) AS sensitiveUsers,
          SUM(CASE WHEN is_key_user = 0 THEN 1 ELSE 0 END) AS normalUsers
        FROM `{self.user_score_table}`
        {where_sql}
        GROUP BY rdt_county_id, rdt_county_name
        ORDER BY totalUsers DESC
        """
        rows = self._fetch_all(sql, params)
        for row in rows:
            for key in ("totalUsers", "keyUsers", "sensitiveUsers", "normalUsers"):
                row[key] = int(row.get(key) or 0)
        return rows

    def stats_for_county(
        self,
        county_id,
        begin_time=None,
        end_time=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
    ):
        where_parts = ["rdt_county_id = :county_id"]
        params = {"county_id": county_id}
        extra_parts, extra_params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        where_parts.extend(extra_parts)
        params.update(extra_params)
        where_sql = "WHERE " + " AND ".join(where_parts)

        sql = f"""
        SELECT
          COUNT(*) AS totalUsers,
          SUM(CASE WHEN is_key_user = 1 THEN 1 ELSE 0 END) AS keyUsers,
          SUM(CASE WHEN is_sensitive_user = 1 THEN 1 ELSE 0 END) AS sensitiveUsers,
          SUM(CASE WHEN is_key_user = 0 THEN 1 ELSE 0 END) AS normalUsers
        FROM `{self.user_score_table}`
        {where_sql}
        """
        result = self._fetch_one(sql, params)
        return {
            "totalUsers": int(result.get("totalUsers") or 0),
            "keyUsers": int(result.get("keyUsers") or 0),
            "sensitiveUsers": int(result.get("sensitiveUsers") or 0),
            "normalUsers": int(result.get("normalUsers") or 0),
        }

    def aggregate_distribution_by_industry(
        self,
        user_level="key",
        rdt_county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
        begin_time=None,
        end_time=None,
    ):
        where_sql, params = self._build_where_clause(
            user_level=user_level,
            rdt_county_id=rdt_county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
            begin_time=begin_time,
            end_time=end_time,
        )
        sql = f"""
        SELECT
          IFNULL(trade_type, '') AS tradeType,
          IFNULL(trade_name, '') AS tradeName,
          COUNT(*) AS userCount
        FROM `{self.user_score_table}`
        {where_sql}
        GROUP BY trade_type, trade_name
        ORDER BY userCount DESC
        """
        return self._fetch_all(sql, params)

    def aggregate_distribution_by_outage_nature(
        self,
        user_level="key",
        rdt_county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
        begin_time=None,
        end_time=None,
    ):
        where_sql, params = self._build_where_clause(
            user_level=user_level,
            rdt_county_id=rdt_county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
            begin_time=begin_time,
            end_time=end_time,
        )
        sql = f"""
        SELECT
          IFNULL(outage_nature, '') AS outageNature,
          COUNT(*) AS userCount
        FROM `{self.user_score_table}`
        {where_sql}
        GROUP BY outage_nature
        ORDER BY userCount DESC
        """
        return self._fetch_all(sql, params)

    def query_identified_users(
        self,
        page,
        per_page,
        user_level=None,
        keyword=None,
        rdt_county_id=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
        begin_time=None,
        end_time=None,
        sort_by="updated_at",
        sort_order="desc",
    ):
        allowed_sort = {
            "id", "created_at", "updated_at",
            "begin_time", "end_time",
        }
        sort_field = sort_by if sort_by in allowed_sort else "updated_at"
        order = "ASC" if str(sort_order).lower() == "asc" else "DESC"

        where_sql, params = self._build_where_clause(
            user_level=user_level,
            keyword=keyword,
            rdt_county_id=rdt_county_id,
            snapshot_date=snapshot_date,
            snapshot_start_date=snapshot_start_date,
            snapshot_end_date=snapshot_end_date,
            begin_time=begin_time,
            end_time=end_time,
        )

        tbl = self.user_score_table
        offset = (page - 1) * per_page
        count_sql = f"SELECT COUNT(*) AS total FROM `{tbl}` {where_sql}"
        total = int(self._fetch_one(count_sql, params).get("total", 0))

        list_params = {**params, "_limit": per_page, "_offset": offset}
        list_sql = f"""
        SELECT
          cons_no AS consNo,
          cons_name AS consName,
          rdt_county_name AS rdtCountyName,
          trade_name AS tradeName,
          outage_nature AS outageNature,
          is_key_user AS isKeyUser,
          is_sensitive_user AS isSensitiveUser
        FROM `{tbl}`
        {where_sql}
        ORDER BY {sort_field} {order}
        LIMIT :_limit OFFSET :_offset
        """
        rows = self._fetch_all(list_sql, list_params)

        for row in rows:
            row["isKeyUser"] = bool(row.get("isKeyUser"))
            row["isSensitiveUser"] = bool(row.get("isSensitiveUser"))

        return rows, total

    def _build_where_clause(
        self,
        user_level=None,
        keyword=None,
        trade_type=None,
        trade_name=None,
        rdt_county_id=None,
        rdt_county_name=None,
        snapshot_date=None,
        snapshot_start_date=None,
        snapshot_end_date=None,
        begin_time=None,
        end_time=None,
    ):
        parts = []
        params = {}

        if user_level == "sensitive":
            parts.append("is_sensitive_user = 1")
        elif user_level == "key":
            parts.append("is_key_user = 1")
        elif user_level == "normal":
            parts.append("is_key_user = 0")
        elif user_level == "key_sensitive":
            parts.append("(is_key_user = 1 OR is_sensitive_user = 1)")

        if keyword:
            parts.append(
                "(cons_name LIKE :kw OR cons_no LIKE :kw OR outage_number LIKE :kw)"
            )
            params["kw"] = f"%{keyword}%"

        if trade_type:
            parts.append("trade_type = :trade_type")
            params["trade_type"] = trade_type
        if trade_name:
            parts.append("trade_name LIKE :trade_name")
            params["trade_name"] = f"%{trade_name}%"
        if rdt_county_id:
            parts.append("rdt_county_id = :rdt_county_id")
            params["rdt_county_id"] = rdt_county_id
        if rdt_county_name:
            parts.append("rdt_county_name LIKE :rdt_county_name")
            params["rdt_county_name"] = f"%{rdt_county_name}%"

        time_parts, time_params = self._time_filters(
            begin_time, end_time,
            snapshot_date, snapshot_start_date, snapshot_end_date,
        )
        parts.extend(time_parts)
        params.update(time_params)

        where_sql = ("WHERE " + " AND ".join(parts)) if parts else ""
        return where_sql, params

    @staticmethod
    def _time_filters(
        begin_time=None, end_time=None, snapshot_date=None,
        snapshot_start_date=None, snapshot_end_date=None,
    ):
        parts = []
        params = {}
        if snapshot_date:
            parts.append("snapshot_date = :snapshot_date")
            params["snapshot_date"] = snapshot_date
        else:
            if snapshot_start_date:
                parts.append("snapshot_date >= :snapshot_start_date")
                params["snapshot_start_date"] = snapshot_start_date
            if snapshot_end_date:
                parts.append("snapshot_date <= :snapshot_end_date")
                params["snapshot_end_date"] = snapshot_end_date
        if begin_time:
            parts.append("`begin_time` >= :filter_begin_time")
            params["filter_begin_time"] = begin_time
        if end_time:
            parts.append("`begin_time` <= :filter_end_time")
            params["filter_end_time"] = end_time
        return parts, params


county_repository = CountyRepository()
