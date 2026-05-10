# Architecture

## Purpose

`solarproxy-smspvs20r1` exists to extract usable solar production data from older SunPower `SMSPVS20R1 / PVS2` hardware and expose it locally.

The preferred path is the local `LAN2` management interface. The collector-stream tooling exists because it was needed to discover how the hardware behaved before the local console path was confirmed.

## Network Model

### LAN2

- Supervisor local management IP: `172.27.153.1/24`
- Access method: direct Ethernet from a Pi or Linux host
- Response format: HTML
- Primary commands:
  - `DeviceList`
  - `DeviceDetails`

### LAN1

- Used for collector/cloud traffic
- Useful for reverse engineering and fallback
- Not the preferred source for the main dashboard

## Data Flow

### Preferred Path

1. `solarproxy.lan2_poller` fetches inverter and supervisor details from `LAN2`
2. `solarproxy.state` updates `data/latest_state.json`
3. `solarproxy.web` serves the local dashboard and APIs
4. `solarproxy.lan2_poller` optionally publishes MQTT discovery and state to Home Assistant

### Secondary Path

1. `solarproxy.collector_proxy` or `solarproxy.sniffer` captures collector traffic
2. `solarproxy.parser` parses payload records
3. `solarproxy.state` maps those records into the same state file
4. `solarproxy.backfill_history` can recover historical samples from captured logs

## State File

Primary local state file:

```text
data/latest_state.json
```

This is the single source consumed by:

- the web dashboard
- JSON API clients
- local debugging

History file:

```text
data/history.jsonl
```

## Main Components

### `solarproxy.lan2_poller`

Responsibilities:

- fetch `DeviceDetails`
- parse HTML fields
- write local state
- append history
- publish MQTT discovery and state

### `solarproxy.web`

Responsibilities:

- render the dashboard
- serve `/api/latest`
- serve `/api/history`

### `solarproxy.state`

Responsibilities:

- define the normalized state structure
- merge collector-derived and console-derived values
- append/load history
- preserve raw records for later debugging

### `solarproxy.collector_proxy`

Responsibilities:

- receive collector traffic
- forward to the real upstream collector
- log request and response bodies
- update local state from intercepted traffic

### `solarproxy.sniffer`

Responsibilities:

- capture traffic passively when active forwarding is not desired

## Why LAN2 Won

The local `LAN2` console became the preferred source because:

- it exposes named fields instead of opaque record indices
- the values match the inverter menu directly
- it avoids collector timing ambiguity
- it maps cleanly into Home Assistant

## Current Home Assistant Model

The project currently publishes the following MQTT-discovered entities:

- AC power
- AC voltage
- AC current
- DC voltage
- DC current
- grid frequency
- today's energy
- lifetime energy
- last polled timestamp

Recommended Energy Dashboard source:

- `sensor.solarproxy_pv_supervisor_lifetime_energy`

