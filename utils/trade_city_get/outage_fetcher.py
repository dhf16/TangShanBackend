"""
Fetch outage dimension data: substation, feeder, equipment hierarchy.

Per month window:
  1. queryOutageList → extract substation + feeder, collect outageNumbers
  2. queryOutageDetail (with same month window) → extract equipment from nested outageEventEquipVos
"""
import requests
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from .db import (
    load_config, ensure_database, get_connection, ensure_outage_tables,
    upsert_substations, upsert_feeders, upsert_equipments, upsert_equipments_feeders,
)
from .token_client import TokenProvider


def generate_monthly_windows(start, end):
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    cur = s.replace(day=1)
    while cur <= e:
        month_end = cur + relativedelta(months=1) - timedelta(days=1)
        window_end = min(month_end, e)
        yield (
            cur.strftime("%Y-%m-%d 00:00:00"),
            window_end.strftime("%Y-%m-%d 23:59:59"),
        )
        cur += relativedelta(months=1)


def api_request_with_retry(token_provider, url, body, max_retries=3):
    for retry in range(max_retries):
        try:
            status_code, resp = token_provider.request(
                url, method="POST", body=body, timeout=60,
            )
            return status_code, resp
        except requests.exceptions.RequestException as e:
            print(f"  [retry] 第{retry+1}次失败: {e}")
            if retry < max_retries - 1:
                time.sleep(5 * (retry + 1))
            else:
                return None, None


def extract_substations_feeders(records):
    substations = {}
    feeders = {}

    for rec in records:
        subs_id = (rec.get("rdtSubsId") or "").strip()
        subs_name = (rec.get("rdtSubsName") or "").strip()
        feeder_id = (rec.get("rdtFeederId") or "").strip()
        feeder_name = (rec.get("rdtFeederName") or "").strip()
        city_id = (rec.get("cityId") or "").strip()
        county_id = (rec.get("countyId") or "").strip()

        if subs_id and subs_name and subs_id not in substations:
            substations[subs_id] = {
                "subs_id": subs_id,
                "subs_name": subs_name,
                "city_id": city_id,
                "county_id": county_id,
            }

        if feeder_id and feeder_name and feeder_id not in feeders:
            feeders[feeder_id] = {
                "feeder_id": feeder_id,
                "feeder_name": feeder_name,
                "subs_id": subs_id,
                "city_id": city_id,
                "county_id": county_id,
            }

    return substations, feeders


def extract_equipments_from_detail(event_record, feeder_id):
    equipments = {}
    equip_feeder_relations = []

    equip_vos = event_record.get("outageEventEquipVos", {})
    records = equip_vos.get("records", [])

    for rec in records:
        equipment_id = (rec.get("equipmentId") or "").strip()
        if not equipment_id:
            continue

        if equipment_id not in equipments:
            equipments[equipment_id] = {
                "equipment_id": equipment_id,
                "equipment_name": (rec.get("equipmentName") or "").strip(),
                "equipment_type": (rec.get("equipmentType") or "").strip(),
                "tg_id": (rec.get("tgId") or "").strip(),
                "tg_name": (rec.get("tgName") or "").strip(),
                "tg_no": (rec.get("tgNo") or "").strip(),
                "pub_pri_flag": (rec.get("pubPriFlag") or "").strip(),
                "maint_group_id": (rec.get("maintGroupId") or "").strip(),
                "county_id": (rec.get("countyId") or "").strip(),
            }

        if feeder_id:
            equip_feeder_relations.append({
                "equipment_id": equipment_id,
                "feeder_id": feeder_id,
            })

    return equipments, equip_feeder_relations


def fetch_and_store(cfg, token_provider, start_date=None, end_date=None):
    api_cfg = cfg["api"]
    list_url = api_cfg["outage_list_url"]
    detail_url = api_cfg["outage_detail_url"]

    start_date = start_date or api_cfg["start_date"]
    end_date = end_date or api_cfg["end_date"]
    per_page = api_cfg.get("per_page", 300)
    max_pages = api_cfg.get("max_pages", 50)

    ensure_database(cfg)
    conn = get_connection(cfg)

    try:
        ensure_outage_tables(conn)

        all_substations = {}
        all_feeders = {}
        all_equipments = {}
        all_relations = []

        windows = list(generate_monthly_windows(start_date, end_date))
        print(f"开始拉取，共 {len(windows)} 个月份窗口")

        for begin_time, end_time in windows:
            month_label = begin_time[:7]

            # ----- Step 1: queryOutageList → substation + feeder + outageNumbers -----
            month_outage_numbers = []
            month_records = 0
            page = 1

            while page <= max_pages:
                body = {
                    "page": page,
                    "perPage": per_page,
                    "sort": "1",
                    "orderBy": "beginTime",
                    "sysSource": 0,
                    "beginTimeFrom": begin_time,
                    "beginTimeTo": end_time,
                }

                status_code, resp = api_request_with_retry(token_provider, list_url, body)

                if not resp or resp.get("status") != "000000":
                    print(f"  [error][list] {month_label} page={page}, status={status_code}")
                    break

                result = resp.get("result", {})
                records = result.get("records", [])
                pages = result.get("pages", 1)

                substations, feeders = extract_substations_feeders(records)
                all_substations.update(substations)
                all_feeders.update(feeders)

                for rec in records:
                    outage_number = (rec.get("outageNumber") or "").strip()
                    if outage_number:
                        month_outage_numbers.append(outage_number)

                month_records += len(records)

                if page >= pages:
                    break
                page += 1

            print(f"  [{month_label}][list] {month_records} 条事件, {len(month_outage_numbers)} 个事件号")

            if not month_outage_numbers:
                time.sleep(2)
                continue

            # ----- Step 2: queryOutageDetail → equipment -----
            batch_size = 10
            month_equipments = {}
            month_relations = []
            outage_feeder_map = {}

            for rec in records:
                outage_number = (rec.get("outageNumber") or "").strip()
                feeder_id = (rec.get("rdtFeederId") or "").strip()
                if outage_number and feeder_id:
                    outage_feeder_map[outage_number] = feeder_id

            for i in range(0, len(month_outage_numbers), batch_size):
                batch = month_outage_numbers[i:i + batch_size]
                page = 1

                while page <= max_pages:
                    body = {
                        "page": page,
                        "perPage": per_page,
                        "sysSource": 0,
                        "beginTime": begin_time,
                        "endTime": end_time,
                        "outageNumbers": batch,
                    }

                    status_code, resp = api_request_with_retry(token_provider, detail_url, body)

                    if not resp or resp.get("status") != "000000":
                        print(f"  [error][detail] {month_label} batch={i//batch_size+1} page={page}, status={status_code}")
                        break

                    result = resp.get("result", {})
                    event_records = result.get("records", [])
                    pages = result.get("pages", 1)

                    for event_rec in event_records:
                        outage_number = (event_rec.get("outageNumber") or "").strip()
                        feeder_id = outage_feeder_map.get(outage_number, "")
                        equipments, relations = extract_equipments_from_detail(event_rec, feeder_id)
                        month_equipments.update(equipments)
                        month_relations.extend(relations)

                    if page >= pages:
                        break
                    page += 1

                time.sleep(1)

            all_equipments.update(month_equipments)
            all_relations.extend(month_relations)

            # 每月 upsert 一次
            upsert_substations(conn, list(all_substations.values()))
            upsert_feeders(conn, list(all_feeders.values()))
            if month_equipments:
                upsert_equipments(conn, list(month_equipments.values()))
            if month_relations:
                seen = set()
                unique = []
                for r in month_relations:
                    key = (r["equipment_id"], r["feeder_id"])
                    if key not in seen:
                        seen.add(key)
                        unique.append(r)
                upsert_equipments_feeders(conn, unique)

            print(f"  [{month_label}][detail] 设备 {len(month_equipments)}, "
                  f"关联 {len(month_relations)}, "
                  f"累计: 变电站 {len(all_substations)} 线路 {len(all_feeders)} "
                  f"设备 {len(all_equipments)} 关联 {len(all_relations)}")

            time.sleep(2)

        print(f"\n完成: 变电站 {len(all_substations)}, 线路 {len(all_feeders)}, "
              f"设备 {len(all_equipments)}, 设备-线路关联 {len(all_relations)}")
        return {
            "substations": len(all_substations),
            "feeders": len(all_feeders),
            "equipments": len(all_equipments),
            "equip_feeder_relations": len(all_relations),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch outage dimension data (substation/feeder/equipment)")
    parser.add_argument("--start", default=None,
                        help="Start date (YYYY-MM-DD), default from config.yaml")
    parser.add_argument("--end", default=None,
                        help="End date (YYYY-MM-DD), default from config.yaml")
    args = parser.parse_args()

    cfg = load_config()
    tp = TokenProvider(cfg["token"])
    overrides = {}
    if args.start:
        overrides["start_date"] = args.start
    if args.end:
        overrides["end_date"] = args.end

    result = fetch_and_store(cfg, tp, **overrides)
    print(f"Result: {result}")
