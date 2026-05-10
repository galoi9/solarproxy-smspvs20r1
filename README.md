# solarproxy-smspvs20r1

Local monitoring and Home Assistant integration for older SunPower `SMSPVS20R1` / `PVS2` hardware with a Fronius IG inverter.

This project is designed for a simple Raspberry Pi install:

1. Put a Pi on your home Wi-Fi
2. Connect the Pi Ethernet port to `LAN2` on the PV Supervisor
3. Clone this repo onto the Pi
4. Fill in two small `.env` files
5. Start the poller and dashboard
6. Let Home Assistant discover the inverter sensors over MQTT

Repository:

- `https://github.com/galoi9/solarproxy-smspvs20r1`

## What This Project Does

- Polls the PV Supervisor local `LAN2` console at `172.27.153.1`
- Parses `DeviceDetails` HTML for the attached inverter and supervisor
- Stores the latest parsed state locally
- Serves a small local dashboard and JSON API
- Publishes inverter data to Home Assistant through MQTT discovery
- Keeps older collector-stream tooling for research and fallback

## Who This Is For

This project is for older SunPower string-inverter systems where:

- the supervisor is an `SMSPVS20R1` or similar `PVS2` family unit
- `LAN2` exposes a local HTML console
- newer `PVS5/PVS6` JSON/local API documentation does not apply

## Quick Answer: What Hardware Setup Do I Need?

Use a Raspberry Pi with:

- built-in Wi-Fi
- built-in Ethernet
- Raspberry Pi OS or Ubuntu Server

Connect it like this:

- `Wi-Fi` -> your normal home LAN
- `Ethernet` -> `LAN2` on the PV Supervisor

That is the intended install model.

## Beginner Install

Read this first:

- `docs/INSTALL.md`

That guide assumes a fresh Pi and walks through:

- cloning the repo
- creating the service user
- copying the example env files
- finding the serial numbers
- enabling the systemd services
- validating the Home Assistant MQTT sensors

## Project Layout

- `solarproxy/lan2_poller.py`
  Polls the local `LAN2` console and can publish MQTT discovery/state.

- `solarproxy/web.py`
  Serves the local dashboard and JSON endpoints.

- `solarproxy/state.py`
  Holds the latest state model, history helpers, and collector compatibility logic.

- `solarproxy/parser.py`
  Parses captured `SMS2DataCollector.aspx` payloads.

- `solarproxy/collector_proxy.py`
  Collector proxy tooling kept for research and fallback.

- `solarproxy/sniffer.py`
  Passive collector-stream capture helper.

- `solarproxy/backfill_history.py`
  Backfills history from previously captured collector logs.

- `deploy/`
  Systemd unit templates and example environment files.

## Supervisor Port Use

For this hardware family:

- use `LAN2` for the local monitoring connection
- `LAN2` uses static IP `172.27.153.1/24`
- `DeviceDetails` returns `HTML`, not JSON

`LAN1` is not the port this project uses for normal installs. It is typically the network/reporting side used by the Supervisor for cloud-bound traffic.

The key local endpoints are:

```text
http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList
http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceDetails&SerialNumber=<serial>
```

## Current Data Source

The dashboard and MQTT integration are intended to use `LAN2` values, because they are cleaner and directly correspond to inverter menu values.

## Confirmed Field Meanings

Directly confirmed from the `LAN2` HTML console and inverter front panel:

- `Energy Produced` -> current day's energy
- `Total Lifetime Energy` -> cumulative inverter lifetime energy in `kWh`
- `Avg AC Power` -> current inverter AC output in `kW`
- `Avg AC Voltage` -> AC voltage in `V`
- `Avg AC Current` -> AC current in `A`
- `Avg DC Voltage` -> DC voltage in `V`
- `Avg DC Current` -> DC current in `A`
- `Avg AC Frequency` -> grid frequency in `Hz`

## Local Dashboard

Run locally:

```bash
python -m solarproxy.web --host 0.0.0.0 --port 8080
```

Endpoints:

- `http://localhost:8080/`
- `http://localhost:8080/api/latest`
- `http://localhost:8080/api/history`

## LAN2 Polling

Poll once:

```bash
python -m solarproxy.lan2_poller \
  --base-url http://172.27.153.1/cgi-bin/dl_cgi \
  --supervisor-serial YOUR_SUPERVISOR_SERIAL \
  --inverter-serial YOUR_INVERTER_SERIAL \
  --once
```

Poll continuously every 60 seconds:

```bash
python -m solarproxy.lan2_poller \
  --base-url http://172.27.153.1/cgi-bin/dl_cgi \
  --supervisor-serial YOUR_SUPERVISOR_SERIAL \
  --inverter-serial YOUR_INVERTER_SERIAL \
  --interval 60
```

## MQTT / Home Assistant

The poller can publish directly into Home Assistant via MQTT discovery.

Example:

```bash
python -m solarproxy.lan2_poller \
  --base-url http://172.27.153.1/cgi-bin/dl_cgi \
  --supervisor-serial YOUR_SUPERVISOR_SERIAL \
  --inverter-serial YOUR_INVERTER_SERIAL \
  --mqtt-host YOUR_MQTT_HOST \
  --mqtt-port 1883 \
  --mqtt-username YOUR_MQTT_USER \
  --mqtt-password YOUR_MQTT_PASSWORD \
  --once
```

Current discovered sensor set:

- `sensor.solarproxy_pv_supervisor_ac_power`
- `sensor.solarproxy_pv_supervisor_ac_voltage`
- `sensor.solarproxy_pv_supervisor_ac_current`
- `sensor.solarproxy_pv_supervisor_dc_voltage`
- `sensor.solarproxy_pv_supervisor_dc_current`
- `sensor.solarproxy_pv_supervisor_grid_frequency`
- `sensor.solarproxy_pv_supervisor_today_s_energy`
- `sensor.solarproxy_pv_supervisor_lifetime_energy`
- `sensor.solarproxy_pv_supervisor_last_polled`

Recommended Home Assistant Energy Dashboard source:

- `sensor.solarproxy_pv_supervisor_lifetime_energy`

Do not use the daily-resetting `today` sensor as the Energy Dashboard source.

## Generic Deployment Files

The files in `deploy/` are templates, not your live machine settings.

Use:

- `deploy/solarproxy-lan2-poller.service`
- `deploy/solarproxy-web.service`
- `deploy/env.lan2-poller.example`
- `deploy/env.lan2-mqtt.example`

The template deployment path is:

```text
/opt/solarproxy-smspvs20r1
```

The template service account is:

```text
solarproxy
```

## Known Limitations

- `Energy Produced` on the console is coarse compared with high-resolution CT-based energy sensors.
- the Supervisor's own refresh cadence is slower than the Pi poll interval
- the MQTT sensor uses `Last Polled`, not the Supervisor's internal `Last Refresh`, because it is easier to understand
- `Avg Heat Sink Temperature` is not always present in the HTML

## Credits

This project was shaped by several community efforts and write-ups:

- `Dukat-Gul/SMS-PVS20R1`
  Directly useful for confirming the `LAN2` / `DeviceDetails` polling model and the general Node-RED extraction approach.
  Repository: `https://github.com/Dukat-Gul/SMS-PVS20R1`

- Scott Gruby's SunPower monitoring write-up
  Useful for the overall Pi-in-the-box architecture and the older comment-thread details about `SMSPVS20R1` behavior.
  Article: `https://blog.gruby.com/2020/04/28/monitoring-a-sunpower-solar-system.html`

- SolarPanelTalk SunPower traffic mirroring thread
  Useful background on collector traffic, record families, and how older SunPower monitoring traffic behaves.
  Thread: `https://www.solarpaneltalk.com/forum/solar-panels-for-home/solar-panel-system-equipment/19587-mirroring-intercepting-sunpower-monitoring-traffic`

- SunPower Reddit discussions around older `PVS2` / `SMSPVS20R1` hardware
  Helpful for confirming that `LAN2` and HTML `DeviceDetails` were the right path on older hardware.

## Additional Documentation

- `docs/INSTALL.md`
- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
