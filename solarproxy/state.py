from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from solarproxy.parser import ParsedRecord

DEFAULT_HISTORY_PATH = Path("data/history.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_compact_timestamp(timestamp_text: str | None) -> datetime | None:
    if not timestamp_text:
        return None
    try:
        return datetime.strptime(timestamp_text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class SolarState:
    updated_at_utc: str = field(default_factory=utc_now_iso)
    data_source: str | None = None
    source_payload_count: int = 0
    source_record_count: int = 0
    latest_record_timestamp: str | None = None
    console_last_refresh_text: str | None = None
    site_id: str | None = None
    supervisor_id: str | None = None
    supervisor_model: str | None = None
    supervisor_firmware: str | None = None
    inverter_id: str | None = None
    inverter_model: str | None = None
    inverter_software_version: str | None = None
    last_handshake_token: str | None = None
    last_upload_timestamp: str | None = None
    latest_status_watts: float | None = None
    latest_status_code: str | None = None
    latest_energy_total: float | None = None
    latest_dc_current_a: float | None = None
    latest_dc_voltage_v: float | None = None
    latest_ac_current_a: float | None = None
    latest_ac_voltage_v: float | None = None
    latest_ac_power_kw: float | None = None
    probable_ac_voltage_v: float | None = None
    probable_ac_current_a: float | None = None
    probable_ac_power_w: float | None = None
    probable_dc_voltage_v: float | None = None
    probable_daily_energy_kwh: float | None = None
    latest_grid_hz: float | None = None
    latest_state_code: str | None = None
    avg_heat_sink_temp_c: float | None = None
    today_energy_kwh: float | None = None
    day_baseline_date: str | None = None
    day_baseline_energy_total: float | None = None
    latest_summary: dict[str, Any] = field(default_factory=dict)
    raw_latest_records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _parse_console_refresh_text(refresh_text: str | None) -> str | None:
    if not refresh_text:
        return None
    cleaned = refresh_text.strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc).strftime("%Y%m%d%H%M%S")
        except ValueError:
            continue
    return None


def _apply_100(state: SolarState, record: ParsedRecord) -> None:
    state.data_source = state.data_source or "collector_stream"
    if len(record.fields) >= 4:
        state.supervisor_id = record.fields[2]
        state.last_upload_timestamp = record.fields[3]


def _apply_102(state: SolarState, record: ParsedRecord) -> None:
    if record.fields:
        state.last_handshake_token = record.fields[0]


def _apply_120(state: SolarState, record: ParsedRecord) -> None:
    state.data_source = state.data_source or "collector_stream"
    if record.fields:
        state.latest_record_timestamp = record.fields[0]
    state.raw_latest_records["120"] = {
        "timestamp": record.fields[0] if len(record.fields) > 0 else None,
        "supervisor_id": record.fields[1] if len(record.fields) > 1 else None,
        "fields": record.fields,
        "raw_line": record.raw_line,
    }
    state.latest_summary = {
        "timestamp": record.fields[0] if len(record.fields) > 0 else None,
        "supervisor_id": record.fields[1] if len(record.fields) > 1 else None,
        "raw_fields": record.fields[2:],
    }


def _apply_122(state: SolarState, record: ParsedRecord) -> None:
    state.data_source = state.data_source or "collector_stream"
    if record.fields:
        state.latest_record_timestamp = record.fields[0]
    if len(record.fields) >= 7:
        state.supervisor_model = record.fields[2]
        state.supervisor_firmware = record.fields[3]
    state.raw_latest_records["122"] = {
        "fields": record.fields,
        "raw_line": record.raw_line,
    }


def _apply_130(state: SolarState, record: ParsedRecord) -> None:
    # Inferred mapping from captured traffic. Raw fields are preserved.
    state.data_source = state.data_source or "collector_stream"
    if record.fields:
        state.latest_record_timestamp = record.fields[0]
    state.raw_latest_records["130"] = {
        "timestamp": record.fields[0] if len(record.fields) > 0 else None,
        "inverter_id": record.fields[1] if len(record.fields) > 1 else None,
        "model": record.fields[2] if len(record.fields) > 2 else None,
        "fields": record.fields,
        "raw_line": record.raw_line,
    }
    if len(record.fields) >= 11:
        state.inverter_id = record.fields[1]
        state.inverter_model = record.fields[2]
        state.latest_energy_total = _to_float(record.fields[4])
        state.latest_dc_current_a = _to_float(record.fields[5])
        state.latest_ac_voltage_v = _to_float(record.fields[6])
        state.latest_ac_current_a = _to_float(record.fields[7])
        state.latest_dc_voltage_v = _to_float(record.fields[9])
        state.probable_ac_voltage_v = state.latest_ac_voltage_v
        state.probable_ac_current_a = state.latest_ac_current_a
        if state.probable_ac_voltage_v is not None and state.probable_ac_current_a is not None:
            state.probable_ac_power_w = round(state.probable_ac_voltage_v * state.probable_ac_current_a, 1)
            state.latest_ac_power_kw = round(state.probable_ac_power_w / 1000.0, 3)
        state.probable_dc_voltage_v = state.latest_dc_voltage_v
        state.probable_daily_energy_kwh = _to_float(record.fields[10])
        state.latest_grid_hz = _to_float(record.fields[12]) if len(record.fields) > 12 else None
        state.latest_state_code = record.fields[13] if len(record.fields) > 13 else None
        _update_daily_energy(state, record.fields[0], state.latest_energy_total)


def _apply_131(state: SolarState, record: ParsedRecord) -> None:
    state.data_source = state.data_source or "collector_stream"
    if record.fields:
        state.latest_record_timestamp = record.fields[0]
    state.raw_latest_records["131"] = {
        "timestamp": record.fields[0] if len(record.fields) > 0 else None,
        "inverter_id": record.fields[1] if len(record.fields) > 1 else None,
        "model": record.fields[2] if len(record.fields) > 2 else None,
        "fields": record.fields,
        "raw_line": record.raw_line,
    }
    if len(record.fields) >= 6:
        state.inverter_id = record.fields[1]
        state.inverter_model = record.fields[2]
        state.latest_status_code = record.fields[3]
        watts = _to_float(record.fields[5])
        state.latest_status_watts = watts


def _update_daily_energy(state: SolarState, timestamp_text: str, energy_total: float | None) -> None:
    if energy_total is None or len(timestamp_text) < 8:
        return
    day = timestamp_text[:8]
    if state.day_baseline_date != day or state.day_baseline_energy_total is None:
        state.day_baseline_date = day
        state.day_baseline_energy_total = energy_total
        state.today_energy_kwh = 0.0
        return
    delta = energy_total - state.day_baseline_energy_total
    state.today_energy_kwh = round(max(delta, 0.0), 4)


def apply_console_snapshot(state: SolarState, snapshot: dict[str, Any]) -> SolarState:
    state.data_source = "lan2_console"
    state.updated_at_utc = utc_now_iso()
    state.console_last_refresh_text = snapshot.get("last_refresh")
    state.latest_record_timestamp = snapshot.get("refresh_compact") or _compact_utc_now()

    state.supervisor_id = snapshot.get("supervisor_id") or state.supervisor_id
    state.supervisor_model = snapshot.get("supervisor_model") or state.supervisor_model
    state.supervisor_firmware = snapshot.get("supervisor_firmware") or state.supervisor_firmware
    state.inverter_id = snapshot.get("inverter_id") or state.inverter_id
    state.inverter_model = snapshot.get("inverter_model") or state.inverter_model
    state.inverter_software_version = snapshot.get("software_version") or state.inverter_software_version

    state.latest_energy_total = snapshot.get("total_lifetime_energy_kwh")
    state.latest_ac_power_kw = snapshot.get("avg_ac_power_kw")
    if state.latest_ac_power_kw is not None:
        state.probable_ac_power_w = round(state.latest_ac_power_kw * 1000.0, 1)
    state.latest_ac_voltage_v = snapshot.get("avg_ac_voltage_v")
    state.latest_ac_current_a = snapshot.get("avg_ac_current_a")
    state.latest_dc_voltage_v = snapshot.get("avg_dc_voltage_v")
    state.latest_dc_current_a = snapshot.get("avg_dc_current_a")
    state.latest_grid_hz = snapshot.get("avg_ac_frequency_hz")
    state.avg_heat_sink_temp_c = snapshot.get("avg_heat_sink_temp_c")

    state.probable_ac_voltage_v = state.latest_ac_voltage_v
    state.probable_ac_current_a = state.latest_ac_current_a
    state.probable_dc_voltage_v = state.latest_dc_voltage_v

    energy_produced_kwh = snapshot.get("energy_produced_kwh")
    if energy_produced_kwh is not None:
        state.today_energy_kwh = energy_produced_kwh
    else:
        _update_daily_energy(state, state.latest_record_timestamp, state.latest_energy_total)

    state.raw_latest_records["lan2_device_details"] = snapshot
    return state


def build_state(records: list[ParsedRecord], payload_count: int) -> SolarState:
    state = SolarState(source_payload_count=payload_count, source_record_count=len(records))
    for record in records:
        if record.record_type == "100":
            _apply_100(state, record)
        elif record.record_type == "102":
            _apply_102(state, record)
        elif record.record_type == "120":
            _apply_120(state, record)
        elif record.record_type == "122":
            _apply_122(state, record)
        elif record.record_type == "130":
            _apply_130(state, record)
        elif record.record_type == "131":
            _apply_131(state, record)
    state.updated_at_utc = utc_now_iso()
    return state


def save_state(state: SolarState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_state_object(path: Path) -> SolarState:
    if not path.exists():
        return SolarState()
    data = json.loads(path.read_text(encoding="utf-8"))
    data = _normalize_state_dict(data)
    return SolarState(**data)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return SolarState().to_dict()
    return _normalize_state_dict(json.loads(path.read_text(encoding="utf-8")))


def _normalize_state_dict(data: dict[str, Any]) -> dict[str, Any]:
    normalized = SolarState().to_dict()
    normalized.update(data)

    raw_130 = normalized.get("raw_latest_records", {}).get("130", {})
    fields = raw_130.get("fields") or []

    def get_field(index: int) -> float | None:
        if index >= len(fields):
            return None
        return _to_float(fields[index])

    latest_ac_voltage_v = get_field(6)
    latest_ac_current_a = get_field(7)
    latest_dc_voltage_v = get_field(9)
    probable_ac_voltage_v = normalized.get("probable_ac_voltage_v")
    probable_ac_current_a = normalized.get("probable_ac_current_a")
    probable_dc_voltage_v = normalized.get("probable_dc_voltage_v")
    probable_daily_energy_kwh = normalized.get("probable_daily_energy_kwh")

    if probable_ac_voltage_v is None:
        probable_ac_voltage_v = latest_ac_voltage_v
    if probable_ac_current_a is None:
        probable_ac_current_a = latest_ac_current_a
    if probable_dc_voltage_v is None:
        probable_dc_voltage_v = latest_dc_voltage_v
    if probable_daily_energy_kwh is None:
        probable_daily_energy_kwh = get_field(10)

    normalized["latest_ac_voltage_v"] = latest_ac_voltage_v
    normalized["latest_ac_current_a"] = latest_ac_current_a
    normalized["latest_dc_voltage_v"] = latest_dc_voltage_v
    normalized["probable_ac_voltage_v"] = probable_ac_voltage_v
    normalized["probable_ac_current_a"] = probable_ac_current_a
    normalized["probable_dc_voltage_v"] = probable_dc_voltage_v
    normalized["probable_daily_energy_kwh"] = probable_daily_energy_kwh

    if normalized.get("latest_ac_power_kw") is not None:
        normalized["probable_ac_power_w"] = round(float(normalized["latest_ac_power_kw"]) * 1000.0, 1)
    elif probable_ac_voltage_v is not None and probable_ac_current_a is not None:
        normalized["probable_ac_power_w"] = round(probable_ac_voltage_v * probable_ac_current_a, 1)
    if normalized.get("probable_ac_power_w") is not None:
        normalized["latest_ac_power_kw"] = round(normalized["probable_ac_power_w"] / 1000.0, 3)

    return normalized


def latest_sample_from_records(records: list[ParsedRecord]) -> dict[str, Any] | None:
    sample: dict[str, Any] = {}
    for record in records:
        if record.record_type == "130" and len(record.fields) >= 14:
            sample["sample_timestamp"] = record.fields[0]
            sample["inverter_id"] = record.fields[1]
            sample["inverter_model"] = record.fields[2]
            sample["energy_total"] = _to_float(record.fields[4])
            sample["dc_current_a"] = _to_float(record.fields[5])
            sample["dc_voltage_v"] = _to_float(record.fields[6])
            sample["field_7_value"] = _to_float(record.fields[7])
            sample["field_9_value"] = _to_float(record.fields[9])
            sample["field_10_value"] = _to_float(record.fields[10])
            sample["probable_ac_voltage_v"] = _to_float(record.fields[6])
            sample["probable_ac_current_a"] = _to_float(record.fields[7])
            if sample["probable_ac_voltage_v"] is not None and sample["probable_ac_current_a"] is not None:
                sample["probable_ac_power_w"] = round(sample["probable_ac_voltage_v"] * sample["probable_ac_current_a"], 1)
            sample["probable_dc_voltage_v"] = _to_float(record.fields[9])
            sample["probable_daily_energy_kwh"] = _to_float(record.fields[10])
            sample["grid_hz"] = _to_float(record.fields[12]) if len(record.fields) > 12 else None
            sample["state_code"] = record.fields[13] if len(record.fields) > 13 else None
            sample["raw_130_fields"] = record.fields
        elif record.record_type == "131" and len(record.fields) >= 6:
            sample["sample_timestamp"] = record.fields[0]
            sample["inverter_id"] = record.fields[1]
            sample["inverter_model"] = record.fields[2]
            sample["status_code"] = record.fields[3]
            sample["status_value"] = _to_int(record.fields[4])
            sample["power_w"] = _to_float(record.fields[5])
            sample["raw_131_fields"] = record.fields
        elif record.record_type == "120" and len(record.fields) >= 2:
            sample["sample_timestamp"] = record.fields[0]
            sample["supervisor_id"] = record.fields[1]
            sample["raw_120_fields"] = record.fields
    if not sample:
        return None
    sample["captured_at_utc"] = utc_now_iso()
    return sample


def latest_sample_from_console(snapshot: dict[str, Any]) -> dict[str, Any]:
    sample_timestamp = snapshot.get("refresh_compact") or _compact_utc_now()
    ac_power_kw = snapshot.get("avg_ac_power_kw")
    ac_power_w = round(ac_power_kw * 1000.0, 1) if ac_power_kw is not None else None
    return {
        "sample_timestamp": sample_timestamp,
        "captured_at_utc": utc_now_iso(),
        "source": "lan2_console",
        "supervisor_id": snapshot.get("supervisor_id"),
        "inverter_id": snapshot.get("inverter_id"),
        "inverter_model": snapshot.get("inverter_model"),
        "software_version": snapshot.get("software_version"),
        "energy_total": snapshot.get("total_lifetime_energy_kwh"),
        "today_energy_kwh": snapshot.get("energy_produced_kwh"),
        "ac_power_kw": ac_power_kw,
        "power_w": ac_power_w,
        "ac_voltage_v": snapshot.get("avg_ac_voltage_v"),
        "ac_current_a": snapshot.get("avg_ac_current_a"),
        "dc_voltage_v": snapshot.get("avg_dc_voltage_v"),
        "dc_current_a": snapshot.get("avg_dc_current_a"),
        "grid_hz": snapshot.get("avg_ac_frequency_hz"),
        "heat_sink_temp_c": snapshot.get("avg_heat_sink_temp_c"),
        "raw_console_snapshot": snapshot,
    }


def append_history_sample(history_path: Path, sample: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, separators=(",", ":")) + "\n")


def load_recent_history(history_path: Path, limit: int = 120) -> list[dict[str, Any]]:
    if not history_path.exists():
        return []
    lines = history_path.read_text(encoding="utf-8").splitlines()
    recent = lines[-limit:]
    items: list[dict[str, Any]] = []
    for line in recent:
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def update_state(current: SolarState, records: list[ParsedRecord], payload_count: int = 1) -> SolarState:
    state = current
    state.source_payload_count += payload_count
    state.source_record_count += len(records)
    for record in records:
        if record.record_type == "100":
            _apply_100(state, record)
        elif record.record_type == "102":
            _apply_102(state, record)
        elif record.record_type == "120":
            _apply_120(state, record)
        elif record.record_type == "122":
            _apply_122(state, record)
        elif record.record_type == "130":
            _apply_130(state, record)
        elif record.record_type == "131":
            _apply_131(state, record)
    state.updated_at_utc = utc_now_iso()
    return state
