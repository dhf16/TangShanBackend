"""
Fetch unique industry data (tradeName/tradeType) from the upstream API
by paginating through queryOutageUserDetail responses.
"""
import requests
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from .db import load_config, ensure_database, get_connection, ensure_trade_industry_table, upsert_industries
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


def extract_unique_industries(records):
    industries = {}
    for rec in records:
        trade_type = (rec.get("tradeType") or "").strip()
        trade_name = (rec.get("tradeName") or "").strip()
        if not trade_type or not trade_name:
            continue
        if trade_type not in industries:
            industries[trade_type] = {
                "trade_type": trade_type,
                "trade_name": trade_name,
                "category_code": trade_type[:2],
                "category_name": "",
                "user_count": 1,
            }
        else:
            industries[trade_type]["user_count"] += 1
    return industries


def fetch_and_store(cfg, token_provider, start_date=None, end_date=None):
    api_cfg = cfg["api"]
    base_url = api_cfg["user_detail_url"]
    start_date = start_date or api_cfg["start_date"]
    end_date = end_date or api_cfg["end_date"]
    per_page = api_cfg.get("per_page", 300)
    max_pages = api_cfg.get("max_pages", 200)

    ensure_database(cfg)
    conn = get_connection(cfg)

    try:
        ensure_trade_industry_table(conn)
        total_records = 0
        total_inserted = 0
        total_updated = 0
        known_industries = {}
        no_new_count = 0
        MAX_NO_NEW = 3

        windows = list(generate_monthly_windows(start_date, end_date))
        total_windows = len(windows)
        print(f"开始拉取，共 {total_windows} 个月份窗口")

        for w_idx, (begin_time, end_time) in enumerate(windows):
            page = 1
            month_records = 0
            month_industries = {}
            new_this_month = 0

            while page <= max_pages:
                body = {
                    "page": page,
                    "perPage": per_page,
                    "sort": "1",
                    "orderBy": "beginTime",
                    "beginTime": begin_time,
                    "endTime": end_time,
                }

                # 超时重试，最多3次
                status_code, resp = None, None
                for retry in range(3):
                    try:
                        status_code, resp = token_provider.request(
                            base_url, method="POST", body=body, timeout=60,
                        )
                        break
                    except requests.exceptions.RequestException as e:
                        print(f"  [retry] {begin_time[:7]} page={page} 第{retry+1}次失败: {e}")
                        if retry < 2:
                            time.sleep(5 * (retry + 1))
                        else:
                            print(f"  [error] {begin_time[:7]} page={page} 重试3次均失败，跳过该页")
                            continue

                if not resp or resp.get("status") != "000000":
                    print(f"  [error] {begin_time[:7]} page={page}, status={status_code}")
                    break

                result = resp.get("result", {})
                records = result.get("records", [])
                pages = result.get("pages", 1)

                industries = extract_unique_industries(records)
                for k, v in industries.items():
                    if k not in month_industries:
                        month_industries[k] = v
                        if k not in known_industries:
                            known_industries[k] = v
                            new_this_month += 1
                    else:
                        month_industries[k]["user_count"] += v["user_count"]

                month_records += len(records)

                if page >= pages:
                    break
                page += 1

            # 每个月拉完后立即存库
            if month_industries:
                ins, upd = upsert_industries(conn, list(month_industries.values()))
                total_inserted += ins
                total_updated += upd

            total_records += month_records

            if new_this_month == 0:
                no_new_count += 1
            else:
                no_new_count = 0

            print(f"  [{begin_time[:7]}] {month_records} 条记录, {len(month_industries)} 个行业 (新增: {new_this_month}), 累计: {len(known_industries)}")

            if no_new_count >= MAX_NO_NEW:
                print(f"  连续 {MAX_NO_NEW} 个月无新行业，提前终止")
                break

            time.sleep(2)

        print(f"\n完成: 扫描 {total_records} 条, 写入 {total_inserted} 条, 更新 {total_updated} 条")
        return {
            "records_scanned": total_records,
            "industries_inserted": total_inserted,
            "industries_updated": total_updated,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch industry data from upstream API and store to MySQL")
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
