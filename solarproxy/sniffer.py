from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from typing import Iterable

from solarproxy.parser import parse_payload
from solarproxy.state import (
    append_history_sample,
    latest_sample_from_records,
    load_state_object,
    save_state,
    update_state,
)


DEFAULT_STATE_PATH = Path("data/latest_state.json")
DEFAULT_HISTORY_PATH = Path("data/history.jsonl")
DEFAULT_LOG_DIR = Path("data/sniffer_logs")

PAYLOAD_LINE_RE = re.compile(r"^\d+\t")
POST_RE = re.compile(r"POST /(Command|Data)/SMS2DataCollector\.aspx HTTP/1\.1")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def iter_tcpdump_lines(interface: str) -> Iterable[str]:
    proc = subprocess.Popen(
        [
            "sudo",
            "tcpdump",
            "-l",
            "-A",
            "-s",
            "0",
            "-i",
            interface,
            "tcp port 80",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")


def extract_payloads(lines: Iterable[str]) -> Iterable[str]:
    collecting = False
    payload_lines: list[str] = []

    for line in lines:
        if POST_RE.search(line):
            if payload_lines:
                yield "\n".join(payload_lines)
                payload_lines = []
            collecting = True
            continue

        if not collecting:
            continue

        if line.startswith(tuple(str(i) for i in range(10))) and " IP " in line:
            if payload_lines:
                yield "\n".join(payload_lines)
                payload_lines = []
            collecting = False
            continue

        stripped = line.strip()
        if PAYLOAD_LINE_RE.match(stripped):
            payload_lines.append(stripped)
            if stripped.startswith("102\t"):
                yield "\n".join(payload_lines)
                payload_lines = []
                collecting = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Passive collector sniffer that updates SolarProxy state.")
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()

    args.log_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()

    for payload in extract_payloads(iter_tcpdump_lines(args.interface)):
        if payload in seen:
            continue
        seen.add(payload)
        stamp = utc_stamp()
        (args.log_dir / f"{stamp}.body.txt").write_text(payload + "\n", encoding="utf-8")
        records = parse_payload(payload)
        if not records:
            continue
        state = load_state_object(args.state_file)
        updated = update_state(state, records, payload_count=1)
        save_state(updated, args.state_file)
        sample = latest_sample_from_records(records)
        if sample:
            append_history_sample(args.history_file, sample)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
