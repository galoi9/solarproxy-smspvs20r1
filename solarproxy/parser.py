from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class ParsedRecord:
    record_type: str
    fields: list[str]
    raw_line: str


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\t" not in line:
            continue
        record_type = line.split("\t", 1)[0]
        if not record_type.isdigit():
            continue
        lines.append(line)
    return lines


def parse_payload(text: str) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    for line in _clean_lines(text):
        fields = line.split("\t")
        records.append(ParsedRecord(record_type=fields[0], fields=fields[1:], raw_line=line))
    return records


def parse_many(payloads: Iterable[str]) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    for payload in payloads:
        records.extend(parse_payload(payload))
    return records

