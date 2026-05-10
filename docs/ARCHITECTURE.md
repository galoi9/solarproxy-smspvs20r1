# Architecture

## Purpose

`solarproxy-smspvs20r1` exists to extract usable solar production data from older SunPower `SMSPVS20R1 / PVS2` hardware and expose it locally.

The preferred path is the local `LAN2` management interface.

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
- Not the port used by the normal install path

## Data Flow

### Preferred Path

1. `solarproxy.lan2_poller` fetches inverter and supervisor details from `LAN2`
2. `solarproxy.state` updates `data/latest_state.json`
3. `solarproxy.web` serves the local dashboard and APIs
4. `solarproxy.lan2_poller` optionally publishes MQTT discovery and state to Home Assistant

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

- collector research and fallback support

### `solarproxy.sniffer`

Responsibilities:

- passive collector capture when needed for research

## Why LAN2 Is Used

`LAN2` is used because:

- it exposes named fields instead of opaque record indices
- the values match the inverter menu directly
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
