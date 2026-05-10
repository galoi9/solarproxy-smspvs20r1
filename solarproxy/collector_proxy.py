from __future__ import annotations

import argparse
import http.client
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import socket
import struct
from typing import Any

from solarproxy.parser import parse_payload
from solarproxy.state import (
    DEFAULT_HISTORY_PATH,
    SolarState,
    append_history_sample,
    latest_sample_from_records,
    load_state_object,
    save_state,
    update_state,
)


DEFAULT_STATE_PATH = Path("data/latest_state.json")
DEFAULT_LOG_DIR = Path("data/collector_logs")
DEFAULT_UPSTREAM_HOST = "collector.sunpowermonitor.com"
DEFAULT_DNS_SERVER = "1.1.1.1"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def ack_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def resolve_a_record(hostname: str, dns_server: str = DEFAULT_DNS_SERVER, timeout: float = 5.0) -> str:
    qid = random.randint(0, 0xFFFF)
    flags = 0x0100  # standard query, recursion desired
    header = struct.pack("!HHHHHH", qid, flags, 1, 0, 0, 0)

    labels = hostname.rstrip(".").split(".")
    question = b"".join(len(label).to_bytes(1, "big") + label.encode("ascii") for label in labels) + b"\x00"
    question += struct.pack("!HH", 1, 1)  # A / IN

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(header + question, (dns_server, 53))
        response, _ = sock.recvfrom(2048)
    finally:
        sock.close()

    if len(response) < 12:
        raise RuntimeError(f"short DNS response for {hostname}")

    resp_id, resp_flags, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", response[:12])
    if resp_id != qid:
        raise RuntimeError(f"mismatched DNS response id for {hostname}")
    if (resp_flags & 0x000F) != 0:
        raise RuntimeError(f"DNS error code {(resp_flags & 0x000F)} for {hostname}")
    if ancount == 0:
        raise RuntimeError(f"no A records returned for {hostname}")

    offset = 12
    for _ in range(qdcount):
        while True:
            length = response[offset]
            offset += 1
            if length == 0:
                break
            offset += length
        offset += 4

    for _ in range(ancount):
        if response[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while True:
                length = response[offset]
                offset += 1
                if length == 0:
                    break
                offset += length
        rtype, rclass, _, rdlength = struct.unpack("!HHIH", response[offset : offset + 10])
        offset += 10
        rdata = response[offset : offset + rdlength]
        offset += rdlength
        if rtype == 1 and rclass == 1 and rdlength == 4:
            return socket.inet_ntoa(rdata)

    raise RuntimeError(f"no usable IPv4 A record for {hostname}")


class ProxyHandler(BaseHTTPRequestHandler):
    state_path: Path = DEFAULT_STATE_PATH
    history_path: Path = DEFAULT_HISTORY_PATH
    log_dir: Path = DEFAULT_LOG_DIR
    upstream_host: str = DEFAULT_UPSTREAM_HOST
    upstream_dns_server: str = DEFAULT_DNS_SERVER

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def _client_headers(self) -> dict[str, str]:
        headers = {}
        for key, value in self.headers.items():
            if key.lower() in {"host", "connection"}:
                continue
            headers[key] = value
        headers["Host"] = self.upstream_host
        headers["Connection"] = "keep-alive"
        return headers

    def _write_log(self, body: bytes) -> str:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_stamp()
        meta = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "client": self.client_address[0],
            "method": self.command,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body_length": len(body),
        }
        (self.log_dir / f"{stamp}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        text = body.decode("utf-8", errors="replace")
        (self.log_dir / f"{stamp}.body.txt").write_text(text, encoding="utf-8")

        records = parse_payload(text)
        if records:
            state = load_state_object(self.state_path)
            updated = update_state(state, records, payload_count=1)
            save_state(updated, self.state_path)
            sample = latest_sample_from_records(records)
            if sample:
                append_history_sample(self.history_path, sample)
        return stamp

    def _write_response_log(
        self,
        stamp: str,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        data: bytes,
        upstream_ip: str | None,
        fallback: bool,
    ) -> None:
        meta_path = self.log_dir / f"{stamp}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["response"] = {
            "status": status,
            "reason": reason,
            "headers": headers,
            "body_length": len(data),
            "upstream_ip": upstream_ip,
            "fallback": fallback,
        }
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        (self.log_dir / f"{stamp}.response.txt").write_text(data.decode("utf-8", errors="replace"), encoding="utf-8")

    def _forward(self, body: bytes) -> tuple[int, str, list[tuple[str, str]], bytes, str]:
        upstream_ip = resolve_a_record(self.upstream_host, self.upstream_dns_server)
        conn = http.client.HTTPConnection(upstream_ip, 80, timeout=30)
        try:
            conn.request(self.command, self.path, body=body, headers=self._client_headers())
            resp = conn.getresponse()
            data = resp.read()
            headers = [(k, v) for k, v in resp.getheaders() if k.lower() != "transfer-encoding"]
            return resp.status, resp.reason, headers, data, upstream_ip
        finally:
            conn.close()

    def _fallback(self) -> tuple[int, str, list[tuple[str, str]], bytes]:
        body = f"1002\t{ack_timestamp()}\r\n".encode("utf-8")
        headers = [
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Content-Type", "text/plain"),
            ("Content-Length", str(len(body))),
            ("Connection", "keep-alive"),
        ]
        return 200, "OK", headers, body

    def _handle(self) -> None:
        body = self._read_body()
        stamp = self._write_log(body)
        try:
            status, reason, headers, data, upstream_ip = self._forward(body)
            fallback = False
        except Exception:
            status, reason, headers, data = self._fallback()
            upstream_ip = None
            fallback = True

        self._write_response_log(stamp, status, reason, headers, data, upstream_ip, fallback)

        self.send_response(status, reason)
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        self._handle()

    def do_GET(self) -> None:
        self._handle()


def main() -> int:
    parser = argparse.ArgumentParser(description="Transparent collector proxy for SunPower PVS traffic.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=80, type=int)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--upstream-host", default=DEFAULT_UPSTREAM_HOST)
    parser.add_argument("--upstream-dns-server", default=DEFAULT_DNS_SERVER)
    args = parser.parse_args()

    ProxyHandler.state_path = args.state_file
    ProxyHandler.history_path = args.history_file
    ProxyHandler.log_dir = args.log_dir
    ProxyHandler.upstream_host = args.upstream_host
    ProxyHandler.upstream_dns_server = args.upstream_dns_server

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"Serving collector proxy on http://{args.host}:{args.port}/ forwarding to {args.upstream_host}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
