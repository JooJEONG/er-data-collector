#!/usr/bin/env python3
"""
전국 응급의료기관 실시간 데이터 수집기
- 공공데이터포털 Open API (주 데이터 소스)
- mediboard.nemc.or.kr API (보조 데이터 소스)

매 30분 GitHub Actions cron으로 실행되어 전국 417개 응급의료기관의
실시간 가용병상, 중환자실, 장비 가용 여부 등을 수집하여 CSV로 저장합니다.
"""

import os
import sys
import csv
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
SERVICE_KEY = os.environ.get("DATA_GO_KR_API_KEY", "")
MEDIBOARD_ENABLED = os.environ.get("MEDIBOARD_ENABLED", "true").lower() == "true"

# 17개 시도
STAGES = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도"
]

# mediboard 지역 코드
MEDIBOARD_REGIONS = {
    "11": "서울특별시", "12": "부산광역시", "13": "인천광역시",
    "14": "대구광역시", "15": "광주광역시", "16": "대전광역시",
    "17": "울산광역시", "21": "경기도", "22": "강원특별자치도",
    "23": "충청북도", "24": "충청남도", "25": "전북특별자치도",
    "26": "전라남도", "27": "경상북도", "28": "경상남도",
    "29": "제주특별자치도", "30": "세종특별자치시"
}

# 데이터 저장 경로 (repo root 기준)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# API 기본 URL
DATA_GO_KR_URL = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"
MEDIBOARD_URL = "https://mediboard.nemc.or.kr/api/v1/dashboard/emergency/hospital"


def fetch_data_go_kr() -> list[dict]:
    """공공데이터포털 API에서 전국 응급의료기관 데이터 수집"""
    if not SERVICE_KEY:
        print("[WARN] DATA_GO_KR_API_KEY 환경변수가 설정되지 않았습니다.")
        return []

    all_items = []
    errors = []

    for stage in STAGES:
        encoded_stage = urllib.parse.quote(stage)
        url = (
            f"{DATA_GO_KR_URL}"
            f"?serviceKey={SERVICE_KEY}"
            f"&STAGE1={encoded_stage}"
            f"&STAGE2="
            f"&pageNo=1"
            f"&numOfRows=500"
        )

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=20)
            raw = resp.read().decode("utf-8")
            root = ET.fromstring(raw)

            result_code = root.find(".//resultCode")
            if result_code is None or result_code.text != "00":
                msg = root.find(".//resultMsg")
                errors.append(f"{stage}: API 에러 - {msg.text if msg is not None else 'Unknown'}")
                continue

            items = root.findall(".//item")
            for item in items:
                record = {"source": "data_go_kr", "region": stage}
                for child in item:
                    record[child.tag] = child.text
                all_items.append(record)

            print(f"  [data.go.kr] {stage}: {len(items)}개 기관")

        except Exception as e:
            errors.append(f"{stage}: {e}")
            print(f"  [data.go.kr] {stage}: 에러 - {e}")

        time.sleep(0.3)  # API 부하 방지

    if errors:
        print(f"  [data.go.kr] 에러 {len(errors)}건: {errors}")

    return all_items


def fetch_mediboard() -> list[dict]:
    """mediboard 비공식 API에서 전국 응급의료기관 데이터 수집 (보조)"""
    if not MEDIBOARD_ENABLED:
        return []

    all_items = []
    errors = []

    for code, name in MEDIBOARD_REGIONS.items():
        url = f"{MEDIBOARD_URL}?emogDesc={code}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            hospitals = data.get("result", {}).get("data", [])

            for h in hospitals:
                record = {"source": "mediboard", "region": name, "regionCode": code}
                record.update(h)
                all_items.append(record)

            print(f"  [mediboard] {name}: {len(hospitals)}개 기관")

        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  [mediboard] {name}: 에러 - {e}")

        time.sleep(0.2)

    if errors:
        print(f"  [mediboard] 에러 {len(errors)}건: {errors}")

    return all_items


def save_to_csv(items: list[dict], source_name: str, collection_time: datetime) -> str:
    """수집 데이터를 일별 CSV 파일에 append"""
    if not items:
        return ""

    date_str = collection_time.strftime("%Y-%m-%d")
    month_dir = DATA_DIR / source_name / collection_time.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    csv_path = month_dir / f"{source_name}_{date_str}.csv"
    file_exists = csv_path.exists()

    # 타임스탬프 추가
    timestamp = collection_time.strftime("%Y-%m-%d %H:%M:%S")
    for item in items:
        item["collected_at"] = timestamp

    # 전체 필드 목록 (기존 파일이 있으면 기존 헤더 유지 + 새 필드 추가)
    if file_exists:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            existing_headers = next(reader)
        all_keys = list(existing_headers)
        for item in items:
            for k in item.keys():
                if k not in all_keys:
                    all_keys.append(k)
    else:
        all_keys_set = set()
        for item in items:
            all_keys_set.update(item.keys())
        # 주요 필드를 앞에 배치
        priority = ["collected_at", "source", "region", "hpid", "dutyName", "hvec", "hvidate"]
        all_keys = [k for k in priority if k in all_keys_set]
        all_keys += sorted(k for k in all_keys_set if k not in priority)

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(items)

    return str(csv_path)


def save_latest_snapshot(items: list[dict], source_name: str, collection_time: datetime):
    """최신 스냅샷을 JSON으로 저장 (대시보드용)"""
    snapshot_dir = DATA_DIR / "latest"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "collected_at": collection_time.strftime("%Y-%m-%d %H:%M:%S KST"),
        "source": source_name,
        "total_hospitals": len(items),
        "regions": {},
        "items": items
    }

    # 지역별 요약
    for item in items:
        region = item.get("region", "unknown")
        if region not in snapshot["regions"]:
            snapshot["regions"][region] = 0
        snapshot["regions"][region] += 1

    path = snapshot_dir / f"latest_{source_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def log_collection(collection_time: datetime, source: str, count: int, 
                   errors: int, duration: float, csv_path: str):
    """수집 로그 기록"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "collection_log.csv"
    file_exists = log_path.exists()

    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "source", "hospitals_collected", "errors",
                "duration_seconds", "csv_path"
            ])
        writer.writerow([
            collection_time.strftime("%Y-%m-%d %H:%M:%S"),
            source,
            count,
            errors,
            f"{duration:.1f}",
            csv_path
        ])


def main():
    collection_time = datetime.now(KST)
    print(f"\n{'='*60}")
    print(f"수집 시작: {collection_time.strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'='*60}")

    total_collected = 0
    total_errors = 0

    # ── 1. 공공데이터포털 수집 ──
    print("\n[1/2] 공공데이터포털 API 수집...")
    t0 = time.time()
    data_go_items = fetch_data_go_kr()
    t1 = time.time()

    if data_go_items:
        csv_path = save_to_csv(data_go_items, "data_go_kr", collection_time)
        save_latest_snapshot(data_go_items, "data_go_kr", collection_time)
        log_collection(collection_time, "data_go_kr", len(data_go_items), 
                      len(STAGES) - len(set(i["region"] for i in data_go_items)),
                      t1 - t0, csv_path)
        total_collected += len(data_go_items)
        print(f"  → {len(data_go_items)}개 기관 수집 완료 ({t1-t0:.1f}초)")
    else:
        log_collection(collection_time, "data_go_kr", 0, len(STAGES), t1 - t0, "")
        print("  → 수집 실패")
        total_errors += 1

    # ── 2. mediboard 수집 (보조) ──
    print("\n[2/2] mediboard API 수집 (보조)...")
    t2 = time.time()
    mediboard_items = fetch_mediboard()
    t3 = time.time()

    if mediboard_items:
        csv_path = save_to_csv(mediboard_items, "mediboard", collection_time)
        save_latest_snapshot(mediboard_items, "mediboard", collection_time)
        log_collection(collection_time, "mediboard", len(mediboard_items),
                      len(MEDIBOARD_REGIONS) - len(set(i["region"] for i in mediboard_items)),
                      t3 - t2, csv_path)
        total_collected += len(mediboard_items)
        print(f"  → {len(mediboard_items)}개 기관 수집 완료 ({t3-t2:.1f}초)")
    else:
        log_collection(collection_time, "mediboard", 0, len(MEDIBOARD_REGIONS), t3 - t2, "")
        print("  → 수집 실패 (비공식 API이므로 무시 가능)")

    # ── 요약 ──
    print(f"\n{'='*60}")
    print(f"수집 완료: 총 {total_collected}개 기관 데이터")
    print(f"소요 시간: {time.time() - t0:.1f}초")
    print(f"{'='*60}")

    # 공공데이터포털 수집이 완전 실패한 경우에만 비정상 종료
    if not data_go_items:
        print("\n[ERROR] 공공데이터포털 수집 실패 - 비정상 종료")
        sys.exit(1)


if __name__ == "__main__":
    main()
