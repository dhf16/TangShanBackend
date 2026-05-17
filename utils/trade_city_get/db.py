import os
import re
import pymysql

from dotenv import load_dotenv

load_dotenv()

_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")

CREATE_TRADE_INDUSTRY = """
CREATE TABLE IF NOT EXISTS trade_industry (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trade_type      VARCHAR(16)  NOT NULL COMMENT '行业编码',
    trade_name      VARCHAR(128) NOT NULL COMMENT '行业名称',
    category_code   VARCHAR(4)   DEFAULT '' COMMENT '行业大类编码(tradeType前2位)',
    category_name   VARCHAR(128) DEFAULT '' COMMENT '行业大类名称',
    user_count      INT          DEFAULT 0 COMMENT '该行业用户数',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_trade_type (trade_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def load_config():
    """Build config dict from environment variables (single source of truth: .env)."""
    _required("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
    return {
        "mysql": {
            "host": os.environ["MYSQL_HOST"],
            "port": int(os.environ.get("MYSQL_PORT", "3306")),
            "user": os.environ["MYSQL_USER"],
            "password": os.environ.get("MYSQL_PASSWORD", ""),
            "database": os.environ["MYSQL_DATABASE"],
            "charset": os.environ.get("MYSQL_CHARSET", "utf8mb4"),
        },
        "api": {
            "user_detail_url": _env("API_USER_DETAIL_URL"),
            "outage_list_url": _env("API_OUTAGE_LIST_URL"),
            "outage_detail_url": _env("API_OUTAGE_DETAIL_URL"),
            "start_date": _env("API_START_DATE", "2025-01-01"),
            "end_date": _env("API_END_DATE", "2026-04-30"),
            "per_page": int(_env("API_PER_PAGE", "300")),
            "max_pages": int(_env("API_MAX_PAGES", "200")),
            "equip_per_page": int(_env("API_EQUIP_PER_PAGE", "500")),
        },
        "token": _build_token_config(),
    }


def _required(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")


def _env(key, default=None):
    return os.environ.get(key, default)


def _build_token_config():
    strategy = _env("TOKEN_STRATEGY", "none")
    cfg = {"strategy": strategy}
    if strategy == "esb":
        cfg["esb"] = {
            "token_url": _env("ESB_TOKEN_URL", ""),
            "esb_app_id": _env("ESB_APP_ID", ""),
            "esb_sign": _env("ESB_SIGN", ""),
            "cache_key": _env("ESB_CACHE_KEY", "esb:access_token"),
            "early_expire_seconds": int(_env("ESB_EARLY_EXPIRE_SECONDS", "120")),
            "redis": _redis_cfg("ESB_REDIS_"),
        }
    elif strategy == "oauth2":
        cfg["oauth2"] = {
            "token_url": _env("OAUTH2_TOKEN_URL", ""),
            "client_id": _env("OAUTH2_CLIENT_ID", ""),
            "client_secret": _env("OAUTH2_CLIENT_SECRET", ""),
            "grant_type": _env("OAUTH2_GRANT_TYPE", "client_credentials"),
            "cache_key": _env("OAUTH2_CACHE_KEY", "oauth2:access_token"),
            "early_expire_seconds": int(_env("OAUTH2_EARLY_EXPIRE_SECONDS", "120")),
            "redis": _redis_cfg("OAUTH2_REDIS_"),
        }
    elif strategy == "redis":
        cfg["redis"] = {
            "key": _env("REDIS_TOKEN_KEY", "esb:access_token"),
            **_redis_cfg("REDIS_"),
        }
    elif strategy == "static":
        cfg["static"] = {"value": _env("STATIC_TOKEN", "")}
    cfg["header_name"] = _env("TOKEN_HEADER_NAME", "x-token")
    cfg["header_prefix"] = _env("TOKEN_HEADER_PREFIX", "")
    cfg["header_prefix_fallbacks"] = [
        f for f in _env("TOKEN_HEADER_PREFIX_FALLBACKS", "Bearer").split(",") if f
    ]
    return cfg


def _redis_cfg(prefix):
    """Read redis connection dict from env vars with the given prefix."""
    return {
        "host": _env(f"{prefix}HOST", "127.0.0.1"),
        "port": int(_env(f"{prefix}PORT", "6379")),
        "password": _env(f"{prefix}PASSWORD", ""),
        "db": int(_env(f"{prefix}DB", "0")),
    }


def get_connection(cfg=None, use_db=True):
    if cfg is None:
        cfg = load_config()
    mysql = cfg["mysql"]
    kwargs = dict(
        host=mysql["host"],
        port=mysql["port"],
        user=mysql["user"],
        password=mysql["password"],
        charset=mysql.get("charset", "utf8mb4"),
        autocommit=False,
    )
    if use_db:
        kwargs["database"] = mysql["database"]
    return pymysql.connect(**kwargs)


def ensure_database(cfg=None):
    if cfg is None:
        cfg = load_config()
    db_name = cfg["mysql"]["database"]
    conn = get_connection(cfg, use_db=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
        conn.commit()
        print(f"[db] database '{db_name}' ready")
    finally:
        conn.close()


def ensure_trade_industry_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TRADE_INDUSTRY)
        cur.execute("SHOW COLUMNS FROM trade_industry")
        existing = {row[0] for row in cur.fetchall()}
        if "raw_json" in existing:
            cur.execute("ALTER TABLE trade_industry DROP COLUMN raw_json")
            print("[db] removed column: raw_json")
    conn.commit()
    print("[db] table 'trade_industry' ready")


def upsert_industries(conn, industries):
    if not industries:
        print("  [db] upsert_industries: 无数据可存")
        return 0, 0
    sql = """
        INSERT INTO trade_industry (trade_type, trade_name, category_code, category_name, user_count)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            trade_name = VALUES(trade_name),
            category_code = VALUES(category_code),
            category_name = VALUES(category_name),
            user_count = user_count + VALUES(user_count),
            updated_at = NOW()
    """
    inserted = 0
    updated = 0
    try:
        with conn.cursor() as cur:
            for ind in industries:
                cur.execute(sql, (
                    ind["trade_type"],
                    ind["trade_name"],
                    ind.get("category_code", ""),
                    ind.get("category_name", ""),
                    ind.get("user_count", 0),
                ))
                inserted += 1
        conn.commit()
        print(f"  [db] upsert完成: {inserted} 条写入")
    except Exception as e:
        print(f"  [db] upsert失败: {e}")
        conn.rollback()
        raise
    return inserted, updated


# ======================================================================
# Region tables: city, county, maint_group
# ======================================================================

CREATE_CITY = """
CREATE TABLE IF NOT EXISTS city (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    city_id     VARCHAR(64)  NOT NULL COMMENT '地市公司ID',
    city_name   VARCHAR(128) NOT NULL COMMENT '地市公司名称',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_city_id (city_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_COUNTY = """
CREATE TABLE IF NOT EXISTS county (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    county_id   VARCHAR(64)  NOT NULL COMMENT '区县公司ID',
    county_name VARCHAR(128) NOT NULL COMMENT '区县公司名称',
    city_id     VARCHAR(64)  NOT NULL COMMENT '所属地市ID',
    org_no      VARCHAR(64)  DEFAULT '' COMMENT '所属下级单位编码',
    org_name    VARCHAR(128) DEFAULT '' COMMENT '所属下级单位名称',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_county_id (county_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_MAINT_GROUP = """
CREATE TABLE IF NOT EXISTS maint_group (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    maint_group_id  VARCHAR(64)  NOT NULL COMMENT '运维班组ID',
    maint_group_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '运维班组名称',
    county_id       VARCHAR(64)  NOT NULL COMMENT '所属区县ID',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_maint_group_id (maint_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def ensure_region_tables(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_CITY)
        cur.execute(CREATE_COUNTY)
        cur.execute(CREATE_MAINT_GROUP)
    conn.commit()
    print("[db] region tables ready")


def upsert_cities(conn, cities):
    if not cities:
        return 0
    sql = """
        INSERT INTO city (city_id, city_name)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE city_name = VALUES(city_name), updated_at = NOW()
    """
    count = 0
    try:
        with conn.cursor() as cur:
            for c in cities:
                cur.execute(sql, (c["city_id"], c["city_name"]))
                count += 1
        conn.commit()
    except Exception as e:
        print(f"  [db] upsert cities 失败: {e}")
        conn.rollback()
        raise
    return count


def upsert_counties(conn, counties):
    if not counties:
        return 0
    sql = """
        INSERT INTO county (county_id, county_name, city_id, org_no, org_name)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            county_name = VALUES(county_name),
            city_id = VALUES(city_id),
            org_no = VALUES(org_no),
            org_name = VALUES(org_name),
            updated_at = NOW()
    """
    count = 0
    try:
        with conn.cursor() as cur:
            for c in counties:
                cur.execute(sql, (
                    c["county_id"], c["county_name"], c["city_id"],
                    c.get("org_no", ""), c.get("org_name", ""),
                ))
                count += 1
        conn.commit()
    except Exception as e:
        print(f"  [db] upsert counties 失败: {e}")
        conn.rollback()
        raise
    return count


def upsert_maint_groups(conn, groups):
    if not groups:
        return 0
    sql = """
        INSERT INTO maint_group (maint_group_id, maint_group_name, county_id)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            maint_group_name = VALUES(maint_group_name),
            county_id = VALUES(county_id),
            updated_at = NOW()
    """
    count = 0
    try:
        with conn.cursor() as cur:
            for g in groups:
                cur.execute(sql, (g["maint_group_id"], g["maint_group_name"], g["county_id"]))
                count += 1
        conn.commit()
    except Exception as e:
        print(f"  [db] upsert maint_groups 失败: {e}")
        conn.rollback()
        raise
    return count


# ======================================================================
# Outage dimension tables: substation, feeder, equipment, equipment_feeder
# ======================================================================

CREATE_SUBSTATION = """
CREATE TABLE IF NOT EXISTS substation (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    subs_id     VARCHAR(128) NOT NULL COMMENT '变电站ID(rdtSubsId)',
    subs_name   VARCHAR(256) NOT NULL COMMENT '变电站名称(rdtSubsName)',
    city_id     VARCHAR(64)  DEFAULT '' COMMENT '所属地市ID',
    county_id   VARCHAR(64)  DEFAULT '' COMMENT '所属区县ID',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_subs_id (subs_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_FEEDER = """
CREATE TABLE IF NOT EXISTS feeder (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    feeder_id   VARCHAR(128) NOT NULL COMMENT '线路ID(rdtFeederId)',
    feeder_name VARCHAR(256) NOT NULL COMMENT '线路名称(rdtFeederName)',
    subs_id     VARCHAR(128) NOT NULL COMMENT '所属变电站ID',
    city_id     VARCHAR(64)  DEFAULT '' COMMENT '所属地市ID',
    county_id   VARCHAR(64)  DEFAULT '' COMMENT '所属区县ID',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_feeder_id (feeder_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_EQUIPMENT = """
CREATE TABLE IF NOT EXISTS equipment (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    equipment_id    VARCHAR(128) NOT NULL COMMENT '设备ID',
    equipment_name  VARCHAR(256) DEFAULT '' COMMENT '设备名称',
    equipment_type  VARCHAR(16)  DEFAULT '' COMMENT '设备类型',
    tg_id           VARCHAR(64)  DEFAULT '' COMMENT '台区ID',
    tg_name         VARCHAR(256) DEFAULT '' COMMENT '台区名称',
    tg_no           VARCHAR(64)  DEFAULT '' COMMENT '台区编号',
    pub_pri_flag    VARCHAR(4)   DEFAULT '' COMMENT '公专变标识 01公变 02专变',
    maint_group_id  VARCHAR(64)  DEFAULT '' COMMENT '运维班组ID',
    county_id       VARCHAR(64)  DEFAULT '' COMMENT '区县ID',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_equipment_id (equipment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_EQUIPMENT_FEEDER = """
CREATE TABLE IF NOT EXISTS equipment_feeder (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    equipment_id VARCHAR(128) NOT NULL COMMENT '设备ID',
    feeder_id    VARCHAR(128) NOT NULL COMMENT '线路ID',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_equip_feeder (equipment_id, feeder_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


CREATE_OUTAGE_USER_FULL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    outage_number         VARCHAR(128) DEFAULT '' COMMENT '停电编号',
    cons_no               VARCHAR(128) DEFAULT '' COMMENT '用户编号',
    cons_name             VARCHAR(256) DEFAULT '' COMMENT '用户名称',
    cons_addr             VARCHAR(512) DEFAULT '' COMMENT '用户地址',
    cons_type_name        VARCHAR(128) DEFAULT '' COMMENT '用户类型名称',
    volt_level            VARCHAR(64)  DEFAULT '' COMMENT '电压等级',
    trade_type            VARCHAR(64)  DEFAULT '' COMMENT '行业编码',
    trade_name            VARCHAR(256) DEFAULT '' COMMENT '行业名称',
    outage_nature         VARCHAR(64)  DEFAULT '' COMMENT '停电性质',
    begin_time            DATETIME NULL COMMENT '停电开始时间',
    end_time              DATETIME NULL COMMENT '复电时间',
    rdt_city_id           VARCHAR(64)  DEFAULT '' COMMENT '地市ID',
    rdt_county_id         VARCHAR(64)  DEFAULT '' COMMENT '区县ID',
    rdt_county_name       VARCHAR(128) DEFAULT '' COMMENT '区县名称',
    rdt_maint_group_id    VARCHAR(64)  DEFAULT '' COMMENT '运维班组ID',
    rdt_maint_group_name  VARCHAR(128) DEFAULT '' COMMENT '运维班组名称',
    equipment_id          VARCHAR(128) DEFAULT '' COMMENT '设备ID',
    equipment_name        VARCHAR(256) DEFAULT '' COMMENT '设备名称',
    equipment_type        VARCHAR(64)  DEFAULT '' COMMENT '设备类型',
    tg_name               VARCHAR(256) DEFAULT '' COMMENT '台区名称',
    is_key_user           TINYINT(1)   DEFAULT 0 COMMENT '是否重点用户',
    is_sensitive_user     TINYINT(1)   DEFAULT 0 COMMENT '是否敏感用户',
    snapshot_date         DATE NULL COMMENT '数据快照日期',
    raw_json              LONGTEXT NULL COMMENT '原始记录',
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_outage_user_time (begin_time, end_time),
    KEY idx_outage_user_snapshot (snapshot_date),
    KEY idx_outage_user_city (rdt_city_id),
    KEY idx_outage_user_county (rdt_county_id),
    KEY idx_outage_user_cons (cons_no),
    KEY idx_outage_user_outage (outage_number),
    KEY idx_outage_user_equipment (equipment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def _user_score_table_name():
    table_name = os.environ.get("MYSQL_USER_SCORE_TABLE", "outage_user_full")
    if not _TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError("MYSQL_USER_SCORE_TABLE must contain only letters, numbers, and underscores")
    return table_name


def ensure_outage_tables(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_SUBSTATION)
        cur.execute(CREATE_FEEDER)
        cur.execute(CREATE_EQUIPMENT)
        cur.execute(CREATE_EQUIPMENT_FEEDER)
        cur.execute(CREATE_OUTAGE_USER_FULL_TEMPLATE.format(
            table_name=_user_score_table_name()
        ))
    conn.commit()
    print("[db] outage tables ready")


def _batch_executemany(conn, sql, rows, table_name):
    """executemany with batch commit (每 2000 条提交一次)."""
    if not rows:
        return 0
    batch_size = 2000
    total = len(rows)
    committed = 0
    try:
        with conn.cursor() as cur:
            for start in range(0, total, batch_size):
                batch = rows[start:start + batch_size]
                cur.executemany(sql, batch)
                conn.commit()
                committed += len(batch)
                if total > batch_size:
                    print(f"    [db] {table_name}: {committed}/{total}")
    except Exception as e:
        print(f"  [db] upsert {table_name} 失败: {e}")
        conn.rollback()
        raise
    return total


def upsert_substations(conn, substations):
    if not substations:
        return 0
    sql = """
        INSERT INTO substation (subs_id, subs_name, city_id, county_id)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            subs_name = VALUES(subs_name),
            city_id = VALUES(city_id),
            county_id = VALUES(county_id),
            updated_at = NOW()
    """
    rows = [(s["subs_id"], s["subs_name"],
             s.get("city_id", ""), s.get("county_id", ""))
            for s in substations]
    return _batch_executemany(conn, sql, rows, "substation")


def upsert_feeders(conn, feeders):
    if not feeders:
        return 0
    sql = """
        INSERT INTO feeder (feeder_id, feeder_name, subs_id, city_id, county_id)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            feeder_name = VALUES(feeder_name),
            subs_id = VALUES(subs_id),
            city_id = VALUES(city_id),
            county_id = VALUES(county_id),
            updated_at = NOW()
    """
    rows = [(f["feeder_id"], f["feeder_name"], f["subs_id"],
             f.get("city_id", ""), f.get("county_id", ""))
            for f in feeders]
    return _batch_executemany(conn, sql, rows, "feeder")


def upsert_equipments(conn, equipments):
    if not equipments:
        return 0
    sql = """
        INSERT INTO equipment (equipment_id, equipment_name, equipment_type,
                               tg_id, tg_name, tg_no, pub_pri_flag,
                               maint_group_id, county_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            equipment_name = VALUES(equipment_name),
            equipment_type = VALUES(equipment_type),
            tg_id = VALUES(tg_id),
            tg_name = VALUES(tg_name),
            tg_no = VALUES(tg_no),
            pub_pri_flag = VALUES(pub_pri_flag),
            maint_group_id = VALUES(maint_group_id),
            county_id = VALUES(county_id),
            updated_at = NOW()
    """
    rows = [(eq["equipment_id"], eq["equipment_name"], eq["equipment_type"],
             eq.get("tg_id", ""), eq.get("tg_name", ""), eq.get("tg_no", ""),
             eq.get("pub_pri_flag", ""),
             eq.get("maint_group_id", ""), eq.get("county_id", ""))
            for eq in equipments]
    return _batch_executemany(conn, sql, rows, "equipment")


def upsert_equipments_feeders(conn, relations):
    if not relations:
        return 0
    sql = """
        INSERT IGNORE INTO equipment_feeder (equipment_id, feeder_id)
        VALUES (%s, %s)
    """
    rows = [(r["equipment_id"], r["feeder_id"]) for r in relations]
    return _batch_executemany(conn, sql, rows, "equipment_feeder")
