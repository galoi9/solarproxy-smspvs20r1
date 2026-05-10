from __future__ import annotations

import argparse
from pathlib import Path

from solarproxy.parser import parse_many
from solarproxy.state import build_state, save_state


DEFAULT_STATE_PATH = Path("data/latest_state.json")


def split_payloads(text: str) -> list[str]:
    parts = [part.strip() for part in text.split("\n---\n")]
    return [part for part in parts if part]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import collector payload text into latest state JSON.")
    parser.add_argument("payload_file", type=Path, help="Text file containing one or more payloads separated by ---")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()

    payload_text = args.payload_file.read_text(encoding="utf-8")
    payloads = split_payloads(payload_text)
    records = parse_many(payloads)
    state = build_state(records, payload_count=len(payloads))
    save_state(state, args.state_file)

    print(f"Imported {len(payloads)} payloads and {len(records)} records into {args.state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

