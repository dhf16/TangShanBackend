"""
Fetch outage dimension data: substation, feeder, equipment hierarchy.

Per month window, call queryOutageDetail with time range + pagination:
  - Event-level pagination via outagePage/outagePerPage
  - Equipment nested in each event's outageEventEquipVos
  - Substation/feeder info from event-level fields (rdtSubsId, rdtFeederId, etc.)
  - Equipment-feeder relation: link via parent event's rdtFeederId (no lookup map needed)
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
    detail_url = api_cfg["outage_detail_url"]

    start_date = start_date or api_cfg["start_date"]
    end_date = end_date or api_cfg["end_date"]
    per_page = api_cfg.get("per_page", 300)
    max_pages = api_cfg.get("max_pages", 50)
    equip_per_page = api_cfg.get("equip_per_page", 500)

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
            month_equipments = {}
            month_relations = []
            month_records = 0
            t0 = time.time()

            outage_page = 1
            while outage_page <= max_pages:
                body = {
                    "outagePage": outage_page,
                    "outagePerPage": per_page,
                    "outageEquipPage": 1,
                    "outageEquipPerPage": equip_per_page,
                    "queryTypes": ["1", "2"],
                    "sysSource": "0",
                    "beginTime": begin_time,
                    "endTime": end_time,
                }

                status_code, resp = api_request_with_retry(
                    token_provider, detail_url, body,
                )

                if not resp or resp.get("status") != "000000":
                    print(f"  [error][detail] {month_label} page={outage_page}, "
                          f"status={status_code}")
                    break

                result = resp.get("result", {})
                event_records = result.get("records", [])
                total_pages = result.get("pages", 1)

                page_equip = 0
                for event_rec in event_records:
                    # substation + feeder: from event-level fields
                    subs, feeds = extract_substations_feeders([event_rec])
                    all_substations.update(subs)
                    all_feeders.update(feeds)

                    # equipment: from nested outageEventEquipVos
                    feeder_id = (event_rec.get("rdtFeederId") or "").strip()
                    equipments, relations = extract_equipments_from_detail(
                        event_rec, feeder_id,
                    )
                    month_equipments.update(equipments)
                    month_relations.extend(relations)
                    page_equip += len(equipments)

                    # warn if equipment was truncated
                    equip_vos = event_rec.get("outageEventEquipVos", {})
                    if equip_vos.get("pages", 1) > 1:
                        on = event_rec.get("outageNumber", "?")
                        print(f"  [warn] Event {on} has {equip_vos.get('total', '?')} "
                              f"equipment records ({equip_vos['pages']} pages). "
                              f"Only page 1 fetched.")

                month_records += len(event_records)
                print(f"  [{month_label}] page {outage_page}/{total_pages}: "
                      f"{len(event_records)} 事件, {page_equip} 设备")

                if outage_page >= total_pages:
                    break
                outage_page += 1

            print(f"  [{month_label}] 拉取完成: {month_records} 事件, "
                  f"设备 {len(month_equipments)}, 关联 {len(month_relations)}, "
                  f"耗时 {time.time()-t0:.1f}s")

            all_equipments.update(month_equipments)
            all_relations.extend(month_relations)

            # monthly upsert
            t1 = time.time()
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
            print(f"  [{month_label}] 写入完成, 耗时 {time.time()-t1:.1f}s, "
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
