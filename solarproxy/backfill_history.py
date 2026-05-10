from __future__ import annotations

import argparse
from pathlib import Path

from solarproxy.parser import parse_payload
from solarproxy.state import DEFAULT_HISTORY_PATH, append_history_sample, latest_sample_from_records


DEFAULT_LOG_DIR = Path("data/collector_logs")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SolarProxy history from captured collector bodies.")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    args.history_file.parent.mkdir(parents=True, exist_ok=True)
    if args.history_file.exists():
        args.history_file.unlink()

    count = 0
    seen: set[tuple[str, float | None]] = set()
    for body_file in sorted(args.log_dir.glob("*.body.txt"))[-args.limit :]:
        payload = body_file.read_text(encoding="utf-8", errors="replace")
        records = parse_payload(payload)
        sample = latest_sample_from_records(records)
        if not sample:
            continue
        key = (sample.get("sample_timestamp") or "", sample.get("power_w"))
        if key in seen:
            continue
        seen.add(key)
        append_history_sample(args.history_file, sample)
        count += 1

    print(f"Backfilled {count} samples into {args.history_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
