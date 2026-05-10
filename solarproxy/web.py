from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from solarproxy.state import load_recent_history, load_state, parse_compact_timestamp


DEFAULT_STATE_PATH = Path("data/latest_state.json")
DEFAULT_HISTORY_PATH = Path("data/history.jsonl")


def stale_status(state: dict) -> tuple[str, str]:
    dt = parse_compact_timestamp(state.get("latest_record_timestamp"))
    if dt is None and state.get("updated_at_utc"):
        try:
            dt = datetime.fromisoformat(state["updated_at_utc"])
        except ValueError:
            dt = None
    if dt is None:
        return "Unknown", "No telemetry timestamp parsed yet."
    age = datetime.now(timezone.utc) - dt
    minutes = int(age.total_seconds() // 60)
    if minutes <= 45:
        return "Live", f"Latest telemetry is {minutes} minutes old."
    if minutes <= 180:
        return "Aging", f"Latest telemetry is {minutes} minutes old."
    hours = round(age.total_seconds() / 3600, 1)
    return "Stale", f"Latest telemetry is {hours} hours old."


def format_sample_time(timestamp_text: str | None) -> str:
    dt = parse_compact_timestamp(timestamp_text)
    if dt is None:
        return "n/a"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def format_iso_time(timestamp_text: str | None) -> str:
    if not timestamp_text:
        return "n/a"
    try:
        dt = datetime.fromisoformat(timestamp_text)
    except ValueError:
        return escape(timestamp_text)
    return dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")


def format_iso_time_multiline(timestamp_text: str | None) -> str:
    if not timestamp_text:
        return "n/a"
    try:
        dt = datetime.fromisoformat(timestamp_text)
    except ValueError:
        return escape(timestamp_text)
    return (
        f"{escape(dt.astimezone().strftime('%Y-%m-%d'))}<br>"
        f"{escape(dt.astimezone().strftime('%I:%M:%S %p'))}"
    )


def as_float(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def display_value(key: str, value) -> str:
    if value in (None, ""):
        return "n/a"
    if key == "updated_at_utc":
        return format_iso_time(str(value))
    if key in {"latest_record_timestamp", "last_upload_timestamp"}:
        return format_sample_time(str(value))
    if key == "latest_energy_total":
        numeric = as_float(value)
        return f"{numeric / 1000.0:.1f}" if numeric is not None else escape(str(value))
    if key in {
        "today_energy_kwh",
        "latest_dc_current_a",
        "latest_ac_current_a",
        "latest_ac_power_kw",
        "latest_grid_hz",
        "probable_daily_energy_kwh",
        "avg_heat_sink_temp_c",
    }:
        numeric = as_float(value)
        return f"{numeric:.2f}" if numeric is not None else escape(str(value))
    if key in {
        "latest_dc_voltage_v",
        "latest_ac_voltage_v",
        "probable_ac_voltage_v",
        "probable_dc_voltage_v",
        "probable_ac_power_w",
        "latest_status_watts",
    }:
        numeric = as_float(value)
        return f"{numeric:.0f}" if numeric is not None else escape(str(value))
    return escape(str(value))


def build_power_points(history: list[dict], limit: int = 24) -> list[dict]:
    points: list[dict] = []
    seen: set[tuple[str, float]] = set()
    for item in history:
        sample_time = item.get("sample_timestamp")
        power = as_float(item.get("power_w"))
        if power is None:
            power = as_float(item.get("probable_ac_power_w"))
        if not sample_time or power is None:
            continue
        key = (sample_time, power)
        if key in seen:
            continue
        seen.add(key)
        points.append({"timestamp": sample_time, "power_w": power, "label": format_sample_time(sample_time)})
    return points[-limit:]


def trend_svg(points: list[dict], width: int = 760, height: int = 180) -> str:
    if len(points) < 2:
        return '<div class="empty">Waiting for enough live samples to draw a trend.</div>'
    values = [point["power_w"] for point in points]
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        max_v += 1.0
        min_v -= 1.0
    left = 16
    right = width - 16
    top = 16
    bottom = height - 28
    x_step = (right - left) / max(len(points) - 1, 1)

    coords: list[tuple[float, float]] = []
    for idx, point in enumerate(points):
        x = left + idx * x_step
        y = bottom - ((point["power_w"] - min_v) / (max_v - min_v)) * (bottom - top)
        coords.append((x, y))

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = " ".join(
        [f"{left:.1f},{bottom:.1f}", *[f"{x:.1f},{y:.1f}" for x, y in coords], f"{right:.1f},{bottom:.1f}"]
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 8}" text-anchor="middle">{escape(point["label"][11:16])}</text>'
        for (x, _), point in zip(coords[:: max(1, len(coords) // 6 or 1)], points[:: max(1, len(points) // 6 or 1)])
    )
    return f"""
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="Recent power trend">
      <rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="#f8f4e8"></rect>
      <polyline points="{area}" fill="rgba(177,77,27,0.12)" stroke="none"></polyline>
      <polyline points="{line}" fill="none" stroke="#b14d1b" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      {labels}
    </svg>
    """


def render_dashboard(state: dict, history: list[dict]) -> str:
    def val(key: str, default: str = "n/a") -> str:
        value = state.get(key)
        return default if value in (None, "") else display_value(key, value)

    def meta_line() -> str:
        supervisor_id = val("supervisor_id")
        inverter_model = val("inverter_model")
        inverter_id = val("inverter_id")
        return (
            f"Supervisor {supervisor_id}. "
            f"Inverter {inverter_model} ({inverter_id})."
        )

    status_label, status_text = stale_status(state)
    points = build_power_points(history)
    trend = trend_svg(points)
    raw = escape(json.dumps(state.get("raw_latest_records", {}), indent=2))
    updated_multiline = format_iso_time_multiline(state.get("updated_at_utc"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SolarProxy</title>
  <style>
    :root {{
      --bg: #f3f0e6;
      --card: #fffdf7;
      --ink: #1f2a20;
      --muted: #596558;
      --accent: #b14d1b;
      --line: #d7cfbf;
    }}
    body {{ margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: radial-gradient(circle at top left, #fff6df, var(--bg)); color: var(--ink); }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 2.4rem; font-weight: 700; letter-spacing: -0.03em; }}
    p {{ color: var(--muted); line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin: 24px 0; }}
    .wide-grid {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; margin: 24px 0; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 10px 30px rgba(80, 60, 20, 0.06); }}
    .label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); font-weight: 700; }}
    .value {{ margin-top: 10px; font-size: clamp(1.65rem, 2.2vw, 2.7rem); font-weight: 700; line-height: 1.06; letter-spacing: -0.03em; overflow-wrap: anywhere; word-break: break-word; }}
    .value-meta {{ font-size: clamp(1.05rem, 1.35vw, 1.45rem); line-height: 1.25; letter-spacing: -0.01em; }}
    .sub {{ margin-top: 10px; font-size: 0.95rem; color: var(--muted); }}
    pre {{ overflow: auto; white-space: pre-wrap; background: #f8f4e8; border-radius: 14px; padding: 16px; border: 1px solid var(--line); }}
    a {{ color: var(--accent); }}
    .lede {{ max-width: 70ch; }}
    .status-live, .status-aging, .status-stale, .status-unknown {{ display: inline-block; padding: 6px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }}
    .status-live {{ background: #e4f2df; color: #28572c; }}
    .status-aging {{ background: #fff0c7; color: #7a5908; }}
    .status-stale {{ background: #fbe0d6; color: #8b3418; }}
    .status-unknown {{ background: #e8e5dd; color: #555247; }}
    .empty {{ color: var(--muted); background: #f8f4e8; border: 1px dashed var(--line); border-radius: 14px; padding: 28px; text-align: center; }}
    .mini-list {{ margin: 14px 0 0; padding: 0; list-style: none; }}
    .mini-list li {{ display: flex; justify-content: space-between; gap: 16px; padding: 9px 0; border-top: 1px solid #eee6d7; color: var(--muted); }}
    .mini-list li strong {{ color: var(--ink); font-weight: 600; }}
    @media (max-width: 900px) {{ .wide-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <h1>SolarProxy</h1>
    <p class="lede">Local view of the PV Supervisor and inverter telemetry. {meta_line()}</p>
    <div class="grid">
      <section class="card"><div class="label">Feed Status</div><div class="value"><span class="status-{status_label.lower()}">{status_label}</span></div><div class="sub">{escape(status_text)}</div></section>
      <section class="card"><div class="label">Updated</div><div class="value value-meta">{updated_multiline}</div><div class="sub">Latest parsed state timestamp</div></section>
      <section class="card"><div class="label">AC Power</div><div class="value">{val("probable_ac_power_w")} W</div><div class="sub">Current inverter AC output from the LAN2 console.</div></section>
      <section class="card"><div class="label">Today's Energy</div><div class="value">{val("today_energy_kwh")} kWh</div><div class="sub">Energy accumulated today from the inverter.</div></section>
      <section class="card"><div class="label">Energy Total</div><div class="value">{val("latest_energy_total")} MWh</div><div class="sub">Lifetime production total from the inverter.</div></section>
      <section class="card"><div class="label">Grid Frequency</div><div class="value">{val("latest_grid_hz")} Hz</div><div class="sub">Current grid frequency from the inverter.</div></section>
      <section class="card"><div class="label">AC Voltage</div><div class="value">{val("latest_ac_voltage_v")} V</div><div class="sub">Current inverter AC voltage.</div></section>
      <section class="card"><div class="label">AC Current</div><div class="value">{val("latest_ac_current_a")} A</div><div class="sub">Current inverter AC output.</div></section>
      <section class="card"><div class="label">DC Voltage</div><div class="value">{val("latest_dc_voltage_v")} V</div><div class="sub">Current panel-side DC voltage.</div></section>
      <section class="card"><div class="label">DC Current</div><div class="value">{val("latest_dc_current_a")} A</div><div class="sub">Current panel-side DC current.</div></section>
      <section class="card"><div class="label">Heat Sink Temp</div><div class="value">{val("avg_heat_sink_temp_c")} °C</div><div class="sub">Current inverter heat sink temperature.</div></section>
    </div>
    <div class="wide-grid">
      <section class="card">
        <div class="label">Recent Power Trend</div>
        <div class="sub">Last {len(points)} unique power samples captured by SolarProxy.</div>
        <div style="margin-top:14px">{trend}</div>
      </section>
      <section class="card">
        <div class="label">Current Snapshot</div>
        <ul class="mini-list">
          <li><span>Last sample</span><strong>{val("latest_record_timestamp")}</strong></li>
          <li><span>Console refresh</span><strong>{escape(state.get("console_last_refresh_text") or "n/a")}</strong></li>
          <li><span>Last upload</span><strong>{val("last_upload_timestamp")}</strong></li>
          <li><span>Payloads parsed</span><strong>{val("source_payload_count")}</strong></li>
          <li><span>Records parsed</span><strong>{val("source_record_count")}</strong></li>
          <li><span>Lifetime energy</span><strong>{val("latest_energy_total")} MWh</strong></li>
        </ul>
      </section>
    </div>
    <section class="card">
      <div class="label">Raw Latest Records</div>
      <pre>{raw}</pre>
      <p>JSON APIs: <a href="/api/latest">/api/latest</a> and <a href="/api/history">/api/history</a></p>
    </section>
  </main>
</body>
</html>"""


class AppHandler(BaseHTTPRequestHandler):
    state_path: Path = DEFAULT_STATE_PATH
    history_path: Path = DEFAULT_HISTORY_PATH

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        state = load_state(self.state_path)
        history = load_recent_history(self.history_path)
        if self.path == "/api/latest":
            body = (json.dumps(state, indent=2) + "\n").encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if self.path == "/api/history":
            body = (json.dumps(history, indent=2) + "\n").encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if self.path == "/":
            body = render_dashboard(state, history).encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a local SolarProxy dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    args = parser.parse_args()

    AppHandler.state_path = args.state_file
    AppHandler.history_path = args.history_file
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Serving SolarProxy on http://{args.host}:{args.port}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
