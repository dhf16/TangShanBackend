"""
Seed equipment & equipment_feeder tables with REAL data from the API.

Strategy:
  1. Truncate both tables
  2. queryOutageList → outageNumber → feederId mapping
  3. queryOutageUserDetail → equipment_id/name/type + outageNumber
  4. Join on outageNumber → equipment_feeder relations
"""
from .token_client import TokenProvider
from .db import load_config, get_connection, ensure_outage_tables

BATCH_SIZE = 500


def api_request(tp, url, body, max_retries=2):
    for retry in range(max_retries):
        try:
            status, resp = tp.request(url, method="POST", body=body, timeout=60)
            if resp and resp.get("status") == "000000":
                return resp
        except Exception as e:
            print(f"  [retry] 第{retry+1}次失败: {e}")
    return None


def seed(cfg=None, max_pages_per_month=5, months=None):
    if cfg is None:
        cfg = load_config()

    tp = TokenProvider(cfg["token"])
    conn = get_connection(cfg)

    try:
        # 1) Truncate
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE equipment_feeder")
            cur.execute("TRUNCATE TABLE equipment")
        conn.commit()
        print("[truncate] equipment + equipment_feeder 已清空")

        ensure_outage_tables(conn)

        api_cfg = cfg["api"]
        detail_url = api_cfg["user_detail_url"]
        list_url = api_cfg["outage_list_url"]
        start_date = api_cfg["start_date"]
        end_date = api_cfg["end_date"]
        per_page = api_cfg.get("per_page", 300)

        # Parse monthly windows
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        windows = []
        cur_date = s.replace(day=1)
        while cur_date <= e:
            me = cur_date + relativedelta(months=1) - timedelta(days=1)
            windows.append((
                cur_date.strftime("%Y-%m-%d 00:00:00"),
                min(me, e).strftime("%Y-%m-%d 23:59:59"),
            ))
            cur_date += relativedelta(months=1)

        if months:
            windows = windows[:months]

        all_equipments = {}   # equipment_id -> dict
        all_ef_pairs = set()  # (equipment_id, feeder_id)

        for begin_time, end_time in windows:
            label = begin_time[:7]
            print(f"\n--- {label} ---")

            # Step A: queryOutageList → outageNumber -> feederId
            outage_to_feeder = {}
            page = 1
            while page <= max_pages_per_month:
                body = {
                    "page": page, "perPage": per_page,
                    "sort": "1", "orderBy": "beginTime", "sysSource": 0,
                    "beginTimeFrom": begin_time, "beginTimeTo": end_time,
                }
                resp = api_request(tp, list_url, body)
                if not resp:
                    break
                records = resp.get("result", {}).get("records", [])
                pages = resp.get("result", {}).get("pages", 1)
                for r in records:
                    on = (r.get("outageNumber") or "").strip()
                    fid = (r.get("rdtFeederId") or "").strip()
                    if on and fid:
                        outage_to_feeder[on] = fid
                if page >= pages:
                    break
                page += 1

            print(f"  [list] outageNumber->feederId: {len(outage_to_feeder)} 条映射")

            # Step B: queryOutageUserDetail → equipment
            month_equipments = {}
            month_ef = set()
            page = 1
            while page <= max_pages_per_month:
                body = {
                    "page": page, "perPage": per_page,
                    "sort": "1", "orderBy": "beginTime",
                    "beginTime": begin_time, "endTime": end_time,
                }
                resp = api_request(tp, detail_url, body)
                if not resp:
                    break
                records = resp.get("result", {}).get("records", [])
                pages = resp.get("result", {}).get("pages", 1)

                for r in records:
                    eid = (r.get("equipmentId") or "").strip()
                    if not eid or eid in month_equipments:
                        continue

                    month_equipments[eid] = (
                        eid,
                        (r.get("equipmentName") or "").strip(),
                        (r.get("equipmentType") or "").strip(),
                    )

                    # Build equipment_feeder relation
                    on = (r.get("outageNumber") or "").strip()
                    feeder_id = outage_to_feeder.get(on, "")
                    if feeder_id:
                        month_ef.add((eid, feeder_id))

                if page >= pages:
                    break
                page += 1

            all_equipments.update(month_equipments)
            all_ef_pairs.update(month_ef)
            print(f"  [detail] 设备: {len(month_equipments)}, 关联: {len(month_ef)}")

        # Step C: Bulk insert
        total_eq = len(all_equipments)
        total_ef = len(all_ef_pairs)
        print(f"\n总计: 设备 {total_eq}, 关联 {total_ef}")

        if total_eq:
            eq_sql = """INSERT IGNORE INTO equipment
                (equipment_id, equipment_name, equipment_type,
                 tg_id, tg_name, tg_no, pub_pri_flag, maint_group_id, county_id)
                VALUES (%s, %s, %s, '', '', '', '', '', '')"""
            eq_rows = list(all_equipments.values())
            with conn.cursor() as cur:
                for i in range(0, len(eq_rows), BATCH_SIZE):
                    cur.executemany(eq_sql, eq_rows[i:i+BATCH_SIZE])
                    conn.commit()
                    print(f"  equipment: {min(i+BATCH_SIZE, len(eq_rows))}/{len(eq_rows)}")

        if total_ef:
            ef_sql = "INSERT IGNORE INTO equipment_feeder (equipment_id, feeder_id) VALUES (%s, %s)"
            ef_rows = list(all_ef_pairs)
            with conn.cursor() as cur:
                for i in range(0, len(ef_rows), BATCH_SIZE):
                    cur.executemany(ef_sql, ef_rows[i:i+BATCH_SIZE])
                    conn.commit()
                    print(f"  equipment_feeder: {min(i+BATCH_SIZE, len(ef_rows))}/{len(ef_rows)}")

        print(f"\n完成: equipment={total_eq}, equipment_feeder={total_ef}")

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed equipment tables from API")
    parser.add_argument("--pages", type=int, default=5, help="Max pages per month per API")
    parser.add_argument("--months", type=int, default=0, help="Only first N months (0=all)")
    args = parser.parse_args()
    seed(max_pages_per_month=args.pages, months=args.months or None)
