import re
from datetime import datetime, timedelta

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

_DATETIME_PARSE = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
_NUM_SEGMENTS = 6


def _parse_dt(value):
    for fmt in _DATETIME_PARSE:
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _build_time_segments(begin_time, end_time, num_segments=_NUM_SEGMENTS):
    dt_begin = _parse_dt(begin_time)
    dt_end = _parse_dt(end_time)
    if dt_begin is None or dt_end is None:
        raise ValueError("Invalid datetime format")
    total = (dt_end - dt_begin).total_seconds()
    seg_seconds = total / num_segments
    boundaries = []
    labels = []
    for i in range(num_segments):
        seg_start = dt_begin + timedelta(seconds=seg_seconds * i)
        seg_end = dt_begin + timedelta(seconds=seg_seconds * (i + 1))
        boundaries.append((seg_start, seg_end))
        labels.append(seg_end.strftime("%Y-%m-%d %H:%M:%S"))
    return boundaries, labels


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
        city_id=None,
    ):
        where_parts, params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        if city_id:
            where_parts.append(
                "rdt_county_id IN (SELECT county_id FROM county WHERE city_id = :city_id)"
            )
            params["city_id"] = city_id
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

        count_sql = f"SELECT COUNT(*) AS total FROM `{tbl}` {where_sql}"
        total = int(self._fetch_one(count_sql, params).get("total", 0))

        offset = (page - 1) * per_page

        list_params = {**params, "_limit": per_page, "_offset": offset}
        list_sql = f"""
        SELECT
          cons_no AS consNo,
          cons_name AS consName,
          rdt_county_name AS rdtCountyName,
          trade_name AS tradeName,
          outage_nature AS outageNature,
          outage_number AS outageNumber,
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

    def query_user_outage_stats(
        self,
        page,
        per_page,
        rdt_county_id=None,
        keyword=None,
        outage_count_filter=None,
        begin_time=None,
        end_time=None,
    ):
        where_parts, params = self._time_filters(begin_time, end_time)

        if rdt_county_id:
            where_parts.append("rdt_county_id = :rdt_county_id")
            params["rdt_county_id"] = rdt_county_id

        if keyword:
            where_parts.append("(cons_name LIKE :kw OR cons_no LIKE :kw)")
            params["kw"] = f"%{keyword}%"

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        having_sql = ""
        if outage_count_filter:
            if outage_count_filter == "3+":
                having_sql = "HAVING COUNT(*) >= 3"
            else:
                having_sql = "HAVING COUNT(*) = :_outage_cnt"
                params["_outage_cnt"] = int(outage_count_filter)

        tbl = self.user_score_table

        count_sql = (
            f"SELECT COUNT(*) AS total FROM ("
            f"SELECT cons_no FROM `{tbl}` {where_sql} "
            f"GROUP BY cons_no {having_sql}"
            f") sub"
        )
        total = int(self._fetch_one(count_sql, params).get("total", 0))

        offset = (page - 1) * per_page
        list_params = {**params, "_limit": per_page, "_offset": offset}
        list_sql = f"""
        SELECT
          cons_no AS consNo,
          IFNULL(MAX(cons_name), '') AS consName,
          IFNULL(MAX(rdt_county_name), '') AS countyName,
          IFNULL(MAX(trade_name), '') AS tradeName,
          COUNT(*) AS outageCount
        FROM `{tbl}`
        {where_sql}
        GROUP BY cons_no
        {having_sql}
        ORDER BY outageCount DESC
        LIMIT :_limit OFFSET :_offset
        """
        rows = self._fetch_all(list_sql, list_params)
        for row in rows:
            row["outageCount"] = int(row.get("outageCount") or 0)

        return rows, total

    def trend_by_time(self, begin_time, end_time, rdt_county_id=None):
        boundaries, labels = _build_time_segments(begin_time, end_time)

        whens = []
        params = {
            "filter_begin_time": begin_time,
            "filter_end_time": end_time,
        }
        for i, (seg_start, seg_end) in enumerate(boundaries, 1):
            op = "<=" if i == len(boundaries) else "<"
            whens.append(
                f"WHEN `begin_time` >= :seg_start_{i} AND `begin_time` {op} :seg_end_{i} "
                f"THEN :label_{i}"
            )
            params[f"seg_start_{i}"] = seg_start.strftime("%Y-%m-%d %H:%M:%S")
            params[f"seg_end_{i}"] = seg_end.strftime("%Y-%m-%d %H:%M:%S")
            params[f"label_{i}"] = labels[i - 1]

        case_sql = "CASE " + " ".join(whens) + " END"

        where_parts = [
            "`begin_time` >= :filter_begin_time",
            "`begin_time` <= :filter_end_time",
        ]
        if rdt_county_id:
            where_parts.append("rdt_county_id = :rdt_county_id")
            params["rdt_county_id"] = rdt_county_id
        where_sql = "WHERE " + " AND ".join(where_parts)

        tbl = self.user_score_table
        sql = f"""
        SELECT
          {case_sql} AS timePoint,
          SUM(CASE WHEN is_key_user = 1 THEN 1 ELSE 0 END) AS keyUsers,
          SUM(CASE WHEN is_sensitive_user = 1 THEN 1 ELSE 0 END) AS sensitiveUsers
        FROM `{tbl}`
        {where_sql}
        GROUP BY timePoint
        ORDER BY timePoint ASC
        """
        rows = self._fetch_all(sql, params)

        result_map = {r["timePoint"]: r for r in rows}
        points = []
        for label in labels:
            if label in result_map:
                row = result_map[label]
                points.append({
                    "timePoint": label,
                    "keyUsers": int(row.get("keyUsers") or 0),
                    "sensitiveUsers": int(row.get("sensitiveUsers") or 0),
                })
            else:
                points.append({"timePoint": label, "keyUsers": 0, "sensitiveUsers": 0})

        return points

    def equipment_impact_stats(
        self, begin_time=None, end_time=None,
        city_id=None, county_id=None,
        snapshot_date=None, snapshot_start_date=None, snapshot_end_date=None,
    ):
        where_parts, params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        if city_id:
            where_parts.append(
                "rdt_county_id IN (SELECT county_id FROM county WHERE city_id = :city_id)"
            )
            params["city_id"] = city_id
        if county_id:
            where_parts.append("rdt_county_id = :county_id")
            params["county_id"] = county_id
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        tbl = self.user_score_table

        stats_sql = f"""
        SELECT
          COUNT(DISTINCT equipment_id) AS equipmentCount,
          COUNT(DISTINCT CASE WHEN is_sensitive_user = 1 THEN cons_no END) AS sensitiveUsers,
          COUNT(DISTINCT CASE WHEN is_key_user = 1 THEN cons_no END) AS keyUsers
        FROM `{tbl}`
        {where_sql}
        """
        stats = self._fetch_one(stats_sql, params)
        total_equip = int(stats.get("equipmentCount") or 0)

        high_impact_sql = f"""
        SELECT COUNT(*) AS highImpactCount FROM (
          SELECT equipment_id
          FROM `{tbl}`
          {where_sql}
            AND is_key_user = 1
          GROUP BY equipment_id
          HAVING COUNT(DISTINCT cons_no) >= 20
        ) sub
        """
        high_impact = self._fetch_one(high_impact_sql, params)
        high_count = int(high_impact.get("highImpactCount") or 0)

        return {
            "equipmentCount": total_equip,
            "sensitiveUsers": int(stats.get("sensitiveUsers") or 0),
            "keyUsers": int(stats.get("keyUsers") or 0),
            "highImpactEquipmentCount": high_count,
            "highImpactPercentage": round(high_count / total_equip * 100, 1) if total_equip else 0,
        }

    def equipment_impact_list(
        self, begin_time=None, end_time=None,
        city_id=None, county_id=None, top=None,
        snapshot_date=None, snapshot_start_date=None, snapshot_end_date=None,
    ):
        where_parts, params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        if city_id:
            where_parts.append("rdt_city_id = :city_id")
            params["city_id"] = city_id
        if county_id:
            where_parts.append("rdt_county_id = :county_id")
            params["county_id"] = county_id
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        limit_sql = ""
        if top:
            limit_sql = f"LIMIT :_top"
            params["_top"] = int(top)

        tbl = self.user_score_table
        sql = f"""
        SELECT
          IFNULL(equipment_id, '') AS equipmentId,
          IFNULL(equipment_name, '') AS equipmentName,
          COUNT(DISTINCT CASE WHEN is_key_user = 1 THEN cons_no END) AS keyUsers,
          COUNT(DISTINCT CASE WHEN is_sensitive_user = 1 THEN cons_no END) AS sensitiveUsers,
          COUNT(DISTINCT outage_number) AS outageCount
        FROM `{tbl}`
        {where_sql}
        GROUP BY equipment_id, equipment_name
        ORDER BY keyUsers DESC, outageCount DESC
        {limit_sql}
        """
        rows = self._fetch_all(sql, params)
        for row in rows:
            for key in ("keyUsers", "sensitiveUsers", "outageCount"):
                row[key] = int(row.get(key) or 0)
        return rows

    def equipment_impact_page(
        self, page, per_page,
        begin_time=None, end_time=None,
        city_id=None, county_id=None,
        snapshot_date=None, snapshot_start_date=None, snapshot_end_date=None,
    ):
        where_parts, params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        if city_id:
            where_parts.append("rdt_city_id = :city_id")
            params["city_id"] = city_id
        if county_id:
            where_parts.append("rdt_county_id = :county_id")
            params["county_id"] = county_id
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        tbl = self.user_score_table

        count_sql = f"""
        SELECT COUNT(*) AS total FROM (
          SELECT equipment_id FROM `{tbl}` {where_sql} GROUP BY equipment_id
        ) sub
        """
        total = int(self._fetch_one(count_sql, params).get("total", 0))

        offset = (page - 1) * per_page
        list_params = {**params, "_limit": per_page, "_offset": offset}
        list_sql = f"""
        SELECT
          IFNULL(equipment_id, '') AS equipmentId,
          IFNULL(equipment_name, '') AS equipmentName,
          COUNT(DISTINCT CASE WHEN is_key_user = 1 THEN cons_no END) AS keyUsers,
          COUNT(DISTINCT CASE WHEN is_sensitive_user = 1 THEN cons_no END) AS sensitiveUsers
        FROM `{tbl}`
        {where_sql}
        GROUP BY equipment_id, equipment_name
        ORDER BY keyUsers DESC
        LIMIT :_limit OFFSET :_offset
        """
        rows = self._fetch_all(list_sql, list_params)
        for row in rows:
            for key in ("keyUsers", "sensitiveUsers"):
                row[key] = int(row.get(key) or 0)
        return rows, total

    def equipment_detail(self, equipment_id):
        tbl = self.user_score_table

        stats_sql = f"""
        SELECT
          IFNULL(equipment_id, '') AS equipmentId,
          IFNULL(equipment_name, '') AS equipmentName,
          IFNULL(equipment_type, '') AS equipmentType,
          COUNT(DISTINCT CASE WHEN is_key_user = 1 THEN cons_no END) AS keyUserCount,
          COUNT(DISTINCT CASE WHEN is_sensitive_user = 1 THEN cons_no END) AS sensitiveUserCount
        FROM `{tbl}`
        WHERE equipment_id = :equipment_id
        GROUP BY equipment_id, equipment_name, equipment_type
        """
        stats = self._fetch_one(stats_sql, {"equipment_id": equipment_id})
        if not stats or not stats.get("equipmentId"):
            return None

        user_fields = """
        SELECT DISTINCT
          cons_no AS consNo,
          IFNULL(cons_name, '') AS consName,
          IFNULL(trade_name, '') AS tradeName,
          IFNULL(rdt_county_name, '') AS countyName,
          IFNULL(cons_addr, '') AS consAddr,
          IFNULL(cons_type_name, '') AS consTypeName,
          IFNULL(volt_level, '') AS voltLevel
        """
        key_sql = (
            f"{user_fields} FROM `{tbl}`"
            f" WHERE equipment_id = :equipment_id AND is_key_user = 1"
        )
        sensitive_sql = (
            f"{user_fields} FROM `{tbl}`"
            f" WHERE equipment_id = :equipment_id AND is_sensitive_user = 1"
        )
        key_users = self._fetch_all(key_sql, {"equipment_id": equipment_id})
        sensitive_users = self._fetch_all(sensitive_sql, {"equipment_id": equipment_id})

        return {
            "equipmentId": stats["equipmentId"],
            "equipmentName": stats["equipmentName"],
            "equipmentType": stats.get("equipmentType", ""),
            "keyUserCount": int(stats.get("keyUserCount") or 0),
            "sensitiveUserCount": int(stats.get("sensitiveUserCount") or 0),
            "keyUsers": key_users,
            "sensitiveUsers": sensitive_users,
        }

    def user_outage_detail(self, cons_no, outage_number):
        tbl = self.user_score_table
        sql = f"""
        SELECT
          cons_no AS consNo,
          IFNULL(cons_name, '') AS consName,
          IFNULL(cons_addr, '') AS consAddr,
          IFNULL(outage_nature, '') AS outageNature,
          IFNULL(equipment_name, '') AS equipmentName,
          IFNULL(tg_name, '') AS tgName,
          IFNULL(trade_name, '') AS tradeName
        FROM `{tbl}`
        WHERE cons_no = :cons_no AND outage_number = :outage_number
        LIMIT 1
        """
        row = self._fetch_one(sql, {"cons_no": cons_no, "outage_number": outage_number})
        return row if row and row.get("consNo") else None

    def user_outage_timeline(self, cons_no, begin_time, end_time, rdt_county_id=None):
        tbl = self.user_score_table

        info_sql = f"""
        SELECT
          cons_no AS consNo,
          IFNULL(cons_name, '') AS consName,
          IFNULL(rdt_county_name, '') AS countyName,
          IFNULL(trade_name, '') AS tradeName,
          IFNULL(cons_addr, '') AS consAddr
        FROM `{tbl}`
        WHERE cons_no = :cons_no
        LIMIT 1
        """
        info = self._fetch_one(info_sql, {"cons_no": cons_no})
        if not info or not info.get("consNo"):
            return None

        where_parts = [
            "cons_no = :cons_no",
            "`begin_time` >= :begin_time",
            "`begin_time` <= :end_time",
        ]
        params = {"cons_no": cons_no, "begin_time": begin_time, "end_time": end_time}
        if rdt_county_id:
            where_parts.append("rdt_county_id = :rdt_county_id")
            params["rdt_county_id"] = rdt_county_id
        where_sql = "WHERE " + " AND ".join(where_parts)

        outages_sql = f"""
        SELECT
          IFNULL(begin_time, '') AS beginTime,
          IFNULL(end_time, '') AS endTime
        FROM `{tbl}`
        {where_sql}
        ORDER BY begin_time DESC
        """
        outages = self._fetch_all(outages_sql, params)

        return {
            **info,
            "outageCount": len(outages),
            "outages": outages,
        }

    def bar_chart_by_maint_group(
        self, county_id, begin_time=None, end_time=None,
        snapshot_date=None, snapshot_start_date=None, snapshot_end_date=None,
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
          IFNULL(rdt_maint_group_id, '') AS maintGroupId,
          IFNULL(rdt_maint_group_name, '') AS maintGroupName,
          SUM(CASE WHEN is_key_user = 1 THEN 1 ELSE 0 END) AS keyUsers,
          SUM(CASE WHEN is_sensitive_user = 1 THEN 1 ELSE 0 END) AS sensitiveUsers
        FROM `{self.user_score_table}`
        {where_sql}
        GROUP BY rdt_maint_group_id, rdt_maint_group_name
        ORDER BY (SUM(CASE WHEN is_key_user = 1 THEN 1 ELSE 0 END)
                + SUM(CASE WHEN is_sensitive_user = 1 THEN 1 ELSE 0 END)) DESC
        """
        rows = self._fetch_all(sql, params)
        for row in rows:
            for key in ("keyUsers", "sensitiveUsers"):
                row[key] = int(row.get(key) or 0)
        return rows

    def outage_freq_distribution(
        self, user_level, begin_time=None, end_time=None,
        rdt_county_id=None, snapshot_date=None,
        snapshot_start_date=None, snapshot_end_date=None,
    ):
        if user_level == "key":
            user_filter = "is_key_user = 1"
        else:
            user_filter = "is_sensitive_user = 1"

        where_parts = [user_filter]
        params = {}
        if rdt_county_id:
            where_parts.append("rdt_county_id = :rdt_county_id")
            params["rdt_county_id"] = rdt_county_id
        time_parts, time_params = self._time_filters(
            begin_time, end_time, snapshot_date, snapshot_start_date, snapshot_end_date
        )
        where_parts.extend(time_parts)
        params.update(time_params)
        where_sql = "WHERE " + " AND ".join(where_parts)

        tbl = self.user_score_table
        sql = f"""
        SELECT
          CASE
            WHEN outage_cnt = 1 THEN '1'
            WHEN outage_cnt = 2 THEN '2'
            WHEN outage_cnt >= 3 THEN '3+'
          END AS bucket,
          COUNT(*) AS userCount
        FROM (
          SELECT cons_no, COUNT(*) AS outage_cnt
          FROM `{tbl}`
          {where_sql}
          GROUP BY cons_no
        ) sub
        GROUP BY bucket
        """
        rows = self._fetch_all(sql, params)
        for row in rows:
            row["userCount"] = int(row.get("userCount") or 0)
        return rows

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
