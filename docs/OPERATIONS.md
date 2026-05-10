# Operations

## Current Working Deployment

Expected repo path on the Pi:

```text
/opt/solarproxy-smspvs20r1
```

## Services

### Poller

Service:

```text
solarproxy-lan2-poller.service
```

Purpose:

- poll `LAN2` every 60 seconds
- update local state
- publish MQTT discovery and state

Key unit file:

```text
deploy/solarproxy-lan2-poller.service
```

Environment file:

```text
/opt/solarproxy-smspvs20r1/.env.lan2-mqtt
```

### Web

Service:

```text
solarproxy-web.service
```

Purpose:

- serve the local dashboard on port `8080`

Key unit file:

```text
deploy/solarproxy-web.service
```

## Common Commands

### Check Poller Status

```bash
systemctl --no-pager --full status solarproxy-lan2-poller.service
```

### Check Web Status

```bash
systemctl --no-pager --full status solarproxy-web.service
```

### Restart Poller

```bash
sudo systemctl restart solarproxy-lan2-poller.service
```

### Restart Web

```bash
sudo systemctl restart solarproxy-web.service
```

### View Recent Poller Logs

```bash
journalctl -u solarproxy-lan2-poller.service -n 50 --no-pager
```

### View Recent Web Logs

```bash
journalctl -u solarproxy-web.service -n 50 --no-pager
```

## Validate LAN2 Directly

### Device List

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList'
```

### Inverter Details

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceDetails&SerialNumber=839116902'
```

### Supervisor Details

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceDetails&SerialNumber=TABD01110332'
```

## Validate State File

```bash
cat /opt/solarproxy-smspvs20r1/data/latest_state.json
```

Things to check:

- `updated_at_utc`
- `latest_record_timestamp`
- `console_last_refresh_text`
- `probable_ac_power_w`
- `latest_energy_total`

## Validate Dashboard

Open:

- `http://<pi-hostname>:8080/`
- `http://<pi-ip>:8080/`

## Validate MQTT

The poller publishes discovery plus a retained state payload.

Main retained state topic:

```text
solarproxy/lan2/state
```

Discovery prefix:

```text
homeassistant
```

Example checks:

```bash
mosquitto_sub -h YOUR_MQTT_HOST -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" -t 'solarproxy/#' -v
mosquitto_sub -h YOUR_MQTT_HOST -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" -t 'homeassistant/sensor/solarproxy/#' -v
```

## Home Assistant Validation

Expected entities:

- `sensor.solarproxy_pv_supervisor_ac_power`
- `sensor.solarproxy_pv_supervisor_ac_voltage`
- `sensor.solarproxy_pv_supervisor_ac_current`
- `sensor.solarproxy_pv_supervisor_dc_voltage`
- `sensor.solarproxy_pv_supervisor_dc_current`
- `sensor.solarproxy_pv_supervisor_grid_frequency`
- `sensor.solarproxy_pv_supervisor_today_s_energy`
- `sensor.solarproxy_pv_supervisor_lifetime_energy`
- `sensor.solarproxy_pv_supervisor_last_polled`

Recommended Energy Dashboard solar source:

- `sensor.solarproxy_pv_supervisor_lifetime_energy`

## Troubleshooting

### Dashboard Looks Stale

Check:

- poller service is running
- `latest_state.json` timestamp is moving
- `LAN2` cable is connected

Remember:

- the Pi poll time and the Supervisor's internal refresh time are different
- the dashboard's relatable timing value is `Last Polled`

### MQTT Sensors Missing

Check:

- Mosquitto is running in Home Assistant
- the credentials in `.env.lan2-mqtt` are valid
- the poller has successfully published since the latest code change

If discovery changed, clear retained topics if needed and republish.

### Weird Single Sample Value

The Supervisor occasionally reports a single odd sample. Validate by:

1. polling again
2. comparing against the inverter front panel
3. comparing against the next poll before changing parsing logic

### LAN2 Not Responding

Check:

- Pi interface is on `172.27.153.x/24`
- cable is in `LAN2`, not `LAN1`
- direct `curl` to `172.27.153.1` works
