"""
Fetch city/county/maint_group hierarchy from queryOutageList API responses.
"""
import requests
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from .db import (
    load_config, ensure_database, get_connection,
    ensure_region_tables, upsert_cities, upsert_counties, upsert_maint_groups,
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


def extract_regions(records):
    """Extract unique city/county/maint_group from records.
    Returns three dedup dicts.
    """
    cities = {}
    counties = {}
    maint_groups = {}
    for rec in records:
        city_id = (rec.get("cityId") or "").strip()
        city_name = (rec.get("cityName") or "").strip()
        county_id = (rec.get("countyId") or "").strip()
        county_name = (rec.get("countyName") or "").strip()
        maint_group_id = (rec.get("maintGroupId") or "").strip()
        maint_group_name = (rec.get("maintGroupName") or "").strip()
        org_no = (rec.get("orgNo") or "").strip()
        org_name = (rec.get("orgName") or "").strip()

        if city_id and city_name and city_id not in cities:
            cities[city_id] = {"city_id": city_id, "city_name": city_name}

        if county_id and county_name and county_id not in counties:
            counties[county_id] = {
                "county_id": county_id,
                "county_name": county_name,
                "city_id": city_id,
                "org_no": org_no,
                "org_name": org_name,
            }

        if maint_group_id and maint_group_id not in maint_groups:
            maint_groups[maint_group_id] = {
                "maint_group_id": maint_group_id,
                "maint_group_name": maint_group_name,
                "county_id": county_id,
            }

    return cities, counties, maint_groups


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


def fetch_and_store(cfg, token_provider, start_date=None, end_date=None):
    api_cfg = cfg["api"]
    base_url = api_cfg["outage_list_url"]
    start_date = start_date or api_cfg["start_date"]
    end_date = end_date or api_cfg["end_date"]
    per_page = api_cfg.get("per_page", 300)
    max_pages = api_cfg.get("max_pages", 200)

    ensure_database(cfg)
    conn = get_connection(cfg)

    try:
        ensure_region_tables(conn)
        total_records = 0
        known_cities = {}
        known_counties = {}
        known_groups = {}
        no_new_count = 0
        MAX_NO_NEW = 3

        windows = list(generate_monthly_windows(start_date, end_date))
        total_windows = len(windows)
        print(f"开始拉取区域数据，共 {total_windows} 个月份窗口")

        for w_idx, (begin_time, end_time) in enumerate(windows):
            page = 1
            month_records = 0
            month_cities = {}
            month_counties = {}
            month_groups = {}
            new_this_month = 0

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

                status_code, resp = api_request_with_retry(token_provider, base_url, body)

                if not resp or resp.get("status") != "000000":
                    print(f"  [error] {begin_time[:7]} page={page}, status={status_code}")
                    break

                result = resp.get("result", {})
                records = result.get("records", [])
                pages = result.get("pages", 1)

                cities, counties, groups = extract_regions(records)

                for k, v in cities.items():
                    if k not in month_cities:
                        month_cities[k] = v
                        if k not in known_cities:
                            known_cities[k] = v
                            new_this_month += 1

                for k, v in counties.items():
                    if k not in month_counties:
                        month_counties[k] = v
                        if k not in known_counties:
                            known_counties[k] = v
                            new_this_month += 1

                for k, v in groups.items():
                    if k not in month_groups:
                        month_groups[k] = v
                        if k not in known_groups:
                            known_groups[k] = v
                            new_this_month += 1

                month_records += len(records)

                if page >= pages:
                    break
                page += 1

            # 每个月拉完后立即存库
            if month_cities:
                upsert_cities(conn, list(month_cities.values()))
            if month_counties:
                upsert_counties(conn, list(month_counties.values()))
            if month_groups:
                upsert_maint_groups(conn, list(month_groups.values()))

            total_records += month_records

            if new_this_month == 0:
                no_new_count += 1
            else:
                no_new_count = 0

            print(f"  [{begin_time[:7]}] {month_records} 条记录, 城市 {len(month_cities)} 区县 {len(month_counties)} 班组 {len(month_groups)} (新增: {new_this_month}), 累计: 城市{len(known_cities)} 区县{len(known_counties)} 班组{len(known_groups)}")

            if no_new_count >= MAX_NO_NEW:
                print(f"  连续 {MAX_NO_NEW} 个月无新区域，提前终止")
                break

            time.sleep(2)

        print(f"\n完成: 扫描 {total_records} 条, 城市 {len(known_cities)} 区县 {len(known_counties)} 班组 {len(known_groups)}")
        return {
            "records_scanned": total_records,
            "cities": len(known_cities),
            "counties": len(known_counties),
            "maint_groups": len(known_groups),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch city/county/maint_group data from upstream API")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD), default from config.yaml")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD), default from config.yaml")
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
