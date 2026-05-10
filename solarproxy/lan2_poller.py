from __future__ import annotations

import argparse
import json
import re
import time
from html import unescape
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from solarproxy.state import (
    DEFAULT_HISTORY_PATH,
    apply_console_snapshot,
    append_history_sample,
    latest_sample_from_console,
    load_state_object,
    save_state,
)

DEFAULT_STATE_PATH = Path("data/latest_state.json")
DEFAULT_BASE_URL = "http://172.27.153.1/cgi-bin/dl_cgi"
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_MQTT_STATE_TOPIC = "solarproxy/lan2/state"

INFO_RE = re.compile(
    r"""<(?P<tag>div|td|span)[^>]*class=["'][^"']*\binfo\b[^"']*["'][^>]*>(?P<content>.*?)</(?P=tag)>""",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _fetch_text(url: str, timeout: float = 15.0) -> str:
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean_fragment(fragment: str) -> str:
    text = TAG_RE.sub("", fragment)
    text = unescape(text).replace("\xa0", " ").replace(";", " ")
    return " ".join(text.split()).strip()


def _extract_info_fragments(html: str) -> list[str]:
    matches = [_clean_fragment(match[1]) for match in INFO_RE.findall(html)]
    return [match for match in matches if match]


def _label_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        return "", text.strip()
    label, value = text.split(":", 1)
    return label.strip(), value.strip()


def _value_at(items: list[str], index: int) -> str | None:
    if index >= len(items):
        return None
    return items[index]


def _number_from_text(text: str | None) -> float | None:
    if not text:
        return None
    match = NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _compact_from_refresh_text(text: str | None) -> str | None:
    if not text:
        return None
    digits = re.findall(r"\d+", text)
    if len(digits) >= 6:
        year, month, day, hour, minute, second = digits[:6]
        return f"{year}{month.zfill(2)}{day.zfill(2)}{hour.zfill(2)}{minute.zfill(2)}{second.zfill(2)}"
    return None


def parse_device_details_html(html: str) -> dict[str, Any]:
    items = _extract_info_fragments(html)
    fields: dict[str, str] = {}
    for item in items:
        label, value = _label_value(item)
        if label:
            fields[label] = value

    return {
        "energy_produced_kwh": _number_from_text(fields.get("Energy Produced")),
        "total_lifetime_energy_kwh": _number_from_text(fields.get("Total Lifetime Energy")),
        "last_refresh": fields.get("Last Refresh"),
        "refresh_compact": _compact_from_refresh_text(fields.get("Last Refresh")),
        "model": fields.get("Model"),
        "serial_number": fields.get("Serial Number"),
        "software_version": fields.get("Software Version"),
        "hardware_version": fields.get("Hardware Version"),
        "avg_ac_power_kw": _number_from_text(fields.get("Avg AC Power")),
        "avg_ac_voltage_v": _number_from_text(fields.get("Avg AC Voltage")),
        "avg_ac_current_a": _number_from_text(fields.get("Avg AC Current")),
        "avg_dc_voltage_v": _number_from_text(fields.get("Avg DC Voltage")),
        "avg_dc_current_a": _number_from_text(fields.get("Avg DC Current")),
        "avg_heat_sink_temp_c": _number_from_text(fields.get("Avg Heat Sink Temperature")),
        "avg_ac_frequency_hz": _number_from_text(fields.get("Avg AC Frequency")),
        "device_ip_address": fields.get("Device IP Address"),
        "error_count": _number_from_text(fields.get("Error Count")),
        "communication_error_count": _number_from_text(fields.get("Communication Error Count")),
        "untransmitted_data_points": _number_from_text(fields.get("Untransmitted Data Points")),
        "avg_cpu_load": _number_from_text(fields.get("Avg CPU Load")),
        "memory_used_kb": _number_from_text(fields.get("Memory Used")),
        "flash_space_available_kb": _number_from_text(fields.get("Flash Space Available")),
        "scan_time_sec": _number_from_text(fields.get("Scan Time")),
        "time_since_powerup_sec": _number_from_text(fields.get("Time Since Powerup")),
        "raw_info_items": items,
        "raw_fields": fields,
    }


def fetch_device_details(base_url: str, serial_number: str) -> dict[str, Any]:
    query = urlencode({"Command": "DeviceDetails", "SerialNumber": serial_number})
    html = _fetch_text(f"{base_url}?{query}")
    parsed = parse_device_details_html(html)
    parsed["serial_number"] = serial_number
    parsed["raw_html"] = html
    return parsed


def fetch_console_snapshot(base_url: str, inverter_serial: str, supervisor_serial: str | None) -> dict[str, Any]:
    inverter = fetch_device_details(base_url, inverter_serial)
    supervisor = fetch_device_details(base_url, supervisor_serial) if supervisor_serial else {}

    snapshot = {
        "supervisor_id": supervisor.get("serial_number") or supervisor_serial,
        "supervisor_model": supervisor.get("hardware_version") or supervisor.get("model"),
        "supervisor_firmware": supervisor.get("software_version"),
        "inverter_id": inverter.get("serial_number") or inverter_serial,
        "inverter_model": inverter.get("model"),
        "software_version": inverter.get("software_version"),
        "last_refresh": inverter.get("last_refresh"),
        "energy_produced_kwh": inverter.get("energy_produced_kwh"),
        "total_lifetime_energy_kwh": inverter.get("total_lifetime_energy_kwh"),
        "avg_ac_power_kw": inverter.get("avg_ac_power_kw"),
        "avg_ac_voltage_v": inverter.get("avg_ac_voltage_v"),
        "avg_ac_current_a": inverter.get("avg_ac_current_a"),
        "avg_dc_voltage_v": inverter.get("avg_dc_voltage_v"),
        "avg_dc_current_a": inverter.get("avg_dc_current_a"),
        "avg_heat_sink_temp_c": inverter.get("avg_heat_sink_temp_c"),
        "avg_ac_frequency_hz": inverter.get("avg_ac_frequency_hz"),
        "refresh_compact": inverter.get("refresh_compact"),
        "console_source": "lan2_device_details",
        "raw_device_details": {
            "inverter": inverter,
            "supervisor": supervisor,
        },
    }
    return snapshot


def poll_once(
    base_url: str,
    inverter_serial: str,
    supervisor_serial: str | None,
    state_path: Path,
    history_path: Path,
) -> dict[str, Any]:
    snapshot = fetch_console_snapshot(base_url, inverter_serial, supervisor_serial)
    state = load_state_object(state_path)
    state = apply_console_snapshot(state, snapshot)
    save_state(state, state_path)
    append_history_sample(history_path, latest_sample_from_console(snapshot))
    return snapshot


def _mqtt_discovery_payloads(
    *,
    discovery_prefix: str,
    state_topic: str,
    availability_topic: str,
    snapshot: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    device = {
        "identifiers": ["solarproxy_smspvs20r1", snapshot.get("supervisor_id")],
        "name": "SolarProxy PV Supervisor",
        "manufacturer": "SunPower",
        "model": snapshot.get("supervisor_model") or "SMSPVS20R1",
        "sw_version": snapshot.get("supervisor_firmware"),
        "connections": [["mac", "00:90:e8:2f:07:7d"]],
    }
    sensors = [
        ("ac_power_w", "AC Power", "W", "power", "measurement", "{{ value_json.ac_power_w }}", None),
        ("ac_voltage_v", "AC Voltage", "V", "voltage", "measurement", "{{ value_json.ac_voltage_v }}", None),
        ("ac_current_a", "AC Current", "A", "current", "measurement", "{{ value_json.ac_current_a }}", None),
        ("dc_voltage_v", "DC Voltage", "V", "voltage", "measurement", "{{ value_json.dc_voltage_v }}", None),
        ("dc_current_a", "DC Current", "A", "current", "measurement", "{{ value_json.dc_current_a }}", None),
        ("grid_hz", "Grid Frequency", "Hz", "frequency", "measurement", "{{ value_json.grid_hz }}", None),
        ("today_energy_kwh", "Today's Energy", "kWh", "energy", "total", "{{ value_json.today_energy_kwh }}", None),
        ("lifetime_energy_kwh", "Lifetime Energy", "kWh", "energy", "total_increasing", "{{ value_json.lifetime_energy_kwh }}", None),
        ("last_polled", "Last Polled", None, "timestamp", None, "{{ value_json.last_polled_iso }}", None),
    ]
    payloads: list[tuple[str, dict[str, Any]]] = []
    for object_id, name, unit, device_class, state_class, value_template, icon in sensors:
        topic = f"{discovery_prefix}/sensor/solarproxy/{object_id}/config"
        payload: dict[str, Any] = {
            "name": name,
            "unique_id": f"solarproxy_{object_id}",
            "state_topic": state_topic,
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "value_template": value_template,
            "device": device,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if state_class:
            payload["state_class"] = state_class
        if icon:
            payload["icon"] = icon
        payloads.append((topic, payload))
    return payloads


def _snapshot_to_mqtt_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    refresh_compact = snapshot.get("refresh_compact")
    last_refresh_iso = None
    if refresh_compact and len(refresh_compact) == 14:
        last_refresh_iso = (
            f"{refresh_compact[:4]}-{refresh_compact[4:6]}-{refresh_compact[6:8]}T"
            f"{refresh_compact[8:10]}:{refresh_compact[10:12]}:{refresh_compact[12:14]}+00:00"
        )
    last_polled_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ac_power_kw = snapshot.get("avg_ac_power_kw")
    ac_power_w = round(ac_power_kw * 1000.0, 1) if ac_power_kw is not None else None
    return {
        "supervisor_id": snapshot.get("supervisor_id"),
        "supervisor_model": snapshot.get("supervisor_model"),
        "supervisor_firmware": snapshot.get("supervisor_firmware"),
        "inverter_id": snapshot.get("inverter_id"),
        "inverter_model": snapshot.get("inverter_model"),
        "inverter_software_version": snapshot.get("software_version"),
        "last_refresh": snapshot.get("last_refresh"),
        "last_refresh_iso": last_refresh_iso,
        "last_polled_iso": last_polled_iso,
        "today_energy_kwh": snapshot.get("energy_produced_kwh"),
        "lifetime_energy_kwh": snapshot.get("total_lifetime_energy_kwh"),
        "ac_power_kw": ac_power_kw,
        "ac_power_w": ac_power_w,
        "ac_voltage_v": snapshot.get("avg_ac_voltage_v"),
        "ac_current_a": snapshot.get("avg_ac_current_a"),
        "dc_voltage_v": snapshot.get("avg_dc_voltage_v"),
        "dc_current_a": snapshot.get("avg_dc_current_a"),
        "grid_hz": snapshot.get("avg_ac_frequency_hz"),
        "data_source": snapshot.get("console_source"),
    }


def publish_mqtt(
    snapshot: dict[str, Any],
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    discovery_prefix: str,
    state_topic: str,
) -> None:
    import paho.mqtt.client as mqtt

    client = mqtt.Client(client_id="solarproxy-lan2", clean_session=True)
    client.username_pw_set(username, password)
    client.connect(host, port, 30)
    client.loop_start()
    availability_topic = "solarproxy/lan2/availability"

    for topic, payload in _mqtt_discovery_payloads(
        discovery_prefix=discovery_prefix,
        state_topic=state_topic,
        availability_topic=availability_topic,
        snapshot=snapshot,
    ):
        info = client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=1, retain=True)
        info.wait_for_publish()

    info = client.publish(availability_topic, "online", qos=1, retain=True)
    info.wait_for_publish()
    info = client.publish(state_topic, json.dumps(_snapshot_to_mqtt_state(snapshot), separators=(",", ":")), qos=1, retain=True)
    info.wait_for_publish()
    client.loop_stop()
    client.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll the SunPower SMS-PVS20R1 LAN2 console.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--inverter-serial", required=True)
    parser.add_argument("--supervisor-serial")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--mqtt-host")
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--mqtt-username")
    parser.add_argument("--mqtt-password")
    parser.add_argument("--mqtt-discovery-prefix", default=DEFAULT_MQTT_DISCOVERY_PREFIX)
    parser.add_argument("--mqtt-state-topic", default=DEFAULT_MQTT_STATE_TOPIC)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        snapshot = poll_once(
            base_url=args.base_url,
            inverter_serial=args.inverter_serial,
            supervisor_serial=args.supervisor_serial,
            state_path=args.state_file,
            history_path=args.history_file,
        )
        if args.mqtt_host and args.mqtt_username and args.mqtt_password:
            publish_mqtt(
                snapshot,
                host=args.mqtt_host,
                port=args.mqtt_port,
                username=args.mqtt_username,
                password=args.mqtt_password,
                discovery_prefix=args.mqtt_discovery_prefix,
                state_topic=args.mqtt_state_topic,
            )
        print(
            "Polled LAN2 console:"
            f" inverter={snapshot.get('inverter_id')}"
            f" power_kw={snapshot.get('avg_ac_power_kw')}"
            f" energy_total_kwh={snapshot.get('total_lifetime_energy_kwh')}"
        )
        if args.once:
            return 0
        time.sleep(max(args.interval, 30))


if __name__ == "__main__":
    raise SystemExit(main())
