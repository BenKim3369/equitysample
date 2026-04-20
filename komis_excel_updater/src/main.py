from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fetch_komis import KomisClient, KomisFetchError
from logger import ManualReviewRow, UpdateLogRow, write_manual_review_log, write_update_log
from update_excel import update_workbook
from utils import choose_workbook_path, ensure_directories, load_config, now_timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOMIS 월평균 원자재 가격 엑셀 업데이트")
    parser.add_argument("--workbook", type=str, default="", help="대상 엑셀 파일 전체 경로 (선택)")
    parser.add_argument("--base-dir", type=str, default="", help="프로젝트 기준 디렉토리 (선택)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    base_dir = Path(args.base_dir).resolve() if args.base_dir else Path(__file__).resolve().parent.parent
    config_path = base_dir / "config" / "mapping.json"
    logs_dir = base_dir / "logs"
    output_dir = base_dir / "output"

    ensure_directories(logs_dir, output_dir)

    if not config_path.exists():
        print(f"[실패] 설정 파일을 찾을 수 없습니다: {config_path}")
        return 1

    config = load_config(config_path)
    timestamp = now_timestamp()

    if args.workbook:
        workbook_path = Path(args.workbook).resolve()
    else:
        workbook_path = choose_workbook_path(base_dir, config.workbook)

    if not workbook_path or not workbook_path.exists():
        print("[실패] 대상 엑셀 파일을 찾지 못했습니다.")
        print(f"- 기본 파일명: {config.workbook.file_pattern}")
        print(f"- 검색 위치: {base_dir}")
        return 1

    print("[정보] 엑셀 파일 탐지 완료:", workbook_path)
    print("[정보] KOMIS 데이터 수집 시작...")

    client = KomisClient()
    update_logs: list[UpdateLogRow] = []
    manual_logs: list[ManualReviewRow] = []

    try:
        records, issues = client.fetch_prices(config.minerals)
        print(f"[정보] KOMIS 수집 완료: {len(records)} 건")

        result = update_workbook(
            workbook_path=workbook_path,
            output_dir=output_dir,
            config=config,
            records=records,
            timestamp=timestamp,
            fetch_issues=issues,
        )
        update_logs = result.update_logs
        manual_logs = result.manual_logs

        print("[완료] 업데이트 파일 저장:", result.output_path)

        for status, count in sorted(result.summary.items()):
            print(f"  - {status}: {count}")

    except KomisFetchError as exc:
        print(f"[실패] KOMIS 수집 오류: {exc}")
        return 2
    except Exception as exc:
        print(f"[실패] 처리 중 예외 발생: {exc}")
        return 3
    finally:
        update_log_path = logs_dir / config.logging.update_log_name_template.format(timestamp=timestamp)
        manual_log_path = logs_dir / config.logging.manual_review_log_name_template.format(timestamp=timestamp)
        write_update_log(update_log_path, update_logs)
        write_manual_review_log(manual_log_path, manual_logs)
        print("[정보] 로그 파일 저장:", update_log_path)
        print("[정보] 수동검토 로그 저장:", manual_log_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
