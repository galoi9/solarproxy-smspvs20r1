# Install Guide

This guide assumes you are starting fresh and want the simplest path:

- Raspberry Pi on your home Wi-Fi
- Raspberry Pi Ethernet connected to `LAN2` on the PV Supervisor
- Home Assistant already running on your network
- Home Assistant Mosquitto add-on already installed

## 1. Hardware Setup

You need:

- Raspberry Pi 3/4 or similar
- microSD card
- Ethernet cable
- Wi-Fi access to your home network

Connect the Pi like this:

- `Pi Wi-Fi` -> home network
- `Pi Ethernet` -> `LAN2` on the PV Supervisor

Do not connect the Pi Ethernet to your normal router for this project.

## 2. Install the Pi OS

Use Raspberry Pi OS Lite or Ubuntu Server.

Make sure:

- SSH is enabled
- the Pi joins your home Wi-Fi
- you know the Pi hostname or IP

## 3. Clone the Repo

```bash
git clone https://github.com/galoi9/solarproxy-smspvs20r1.git /opt/solarproxy-smspvs20r1
cd /opt/solarproxy-smspvs20r1
```

## 4. Create a Service User

```bash
sudo useradd --system --create-home --home-dir /opt/solarproxy-smspvs20r1 --shell /usr/sbin/nologin solarproxy || true
sudo chown -R solarproxy:solarproxy /opt/solarproxy-smspvs20r1
```

If you cloned as another user first, run the `chown` command after the clone.

## 5. Install Python Requirements

This project is intentionally light. On Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-paho-mqtt
```

## 6. Put the Pi Ethernet on the LAN2 Network

Set the Ethernet interface to a static `172.27.153.x/24` address.

Example:

```bash
sudo ip addr flush dev eth0
sudo ip addr add 172.27.153.254/24 dev eth0
sudo ip link set eth0 up
```

Test access:

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList'
```

If that works, you are on the right port and subnet.

## 7. Find Your Serial Numbers

Use:

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList'
```

You need:

- the PV Supervisor serial
- the inverter serial

Then confirm both:

```bash
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceDetails&SerialNumber=YOUR_SUPERVISOR_SERIAL'
curl -s 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceDetails&SerialNumber=YOUR_INVERTER_SERIAL'
```

## 8. Create the Poller Config

Copy the example:

```bash
cp deploy/env.lan2-poller.example .env.lan2-poller
```

Edit it:

```text
LAN2_BASE_URL=http://172.27.153.1/cgi-bin/dl_cgi
SUPERVISOR_SERIAL=YOUR_SUPERVISOR_SERIAL
INVERTER_SERIAL=YOUR_INVERTER_SERIAL
POLL_INTERVAL_SECONDS=60
```

## 9. Create the MQTT Config

Copy the example:

```bash
cp deploy/env.lan2-mqtt.example .env.lan2-mqtt
```

Edit it:

```text
MQTT_HOST=homeassistant.local
MQTT_PORT=1883
MQTT_USERNAME=YOUR_MQTT_USER
MQTT_PASSWORD=YOUR_MQTT_PASSWORD
```

## 10. Test the Poller Manually

```bash
python3 -m solarproxy.lan2_poller \
  --base-url http://172.27.153.1/cgi-bin/dl_cgi \
  --supervisor-serial YOUR_SUPERVISOR_SERIAL \
  --inverter-serial YOUR_INVERTER_SERIAL \
  --mqtt-host YOUR_MQTT_HOST \
  --mqtt-port 1883 \
  --mqtt-username YOUR_MQTT_USER \
  --mqtt-password YOUR_MQTT_PASSWORD \
  --once
```

If that works, Home Assistant should discover the `SolarProxy PV Supervisor` sensors.

## 11. Install the Systemd Services

```bash
sudo cp deploy/solarproxy-lan2-poller.service /etc/systemd/system/
sudo cp deploy/solarproxy-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now solarproxy-lan2-poller.service
sudo systemctl enable --now solarproxy-web.service
```

## 12. Check the Services

```bash
systemctl --no-pager --full status solarproxy-lan2-poller.service
systemctl --no-pager --full status solarproxy-web.service
```

## 13. Open the Local Dashboard

```text
http://<pi-ip>:8080/
```

You should see:

- AC power
- AC/DC voltage
- AC/DC current
- grid frequency
- today's energy
- lifetime energy
- last polled

## 14. Add It to Home Assistant Energy Dashboard

Use:

- `sensor.solarproxy_pv_supervisor_lifetime_energy`

Do not use:

- `sensor.solarproxy_pv_supervisor_today_s_energy`

The lifetime energy sensor is the correct `total_increasing` source for the Energy Dashboard.

## 15. Troubleshooting

### `DeviceList` does not work

Check:

- the Pi Ethernet is plugged into `LAN2`
- the Pi Ethernet is on `172.27.153.x/24`
- the PV Supervisor is powered

### MQTT sensors do not appear

Check:

- Home Assistant Mosquitto is running
- the MQTT credentials are correct
- the manual `--once` poll succeeds

### The dashboard is live but Home Assistant is not

This usually means:

- LAN2 polling works
- MQTT credentials or discovery publishing needs attention

Run the manual one-shot poll again and inspect MQTT topics if needed.
