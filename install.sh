#!/bin/bash
# pimusicdevice — one-command Raspberry Pi setup.
#
#     bash install.sh
#
# Idempotent: safe to re-run at any time (re-runs just refresh each step).
# Assumes Raspberry Pi OS Bookworm Lite and a user with sudo (the default
# `pi` user is fine). When it finishes, `sudo reboot` — the device UI
# starts automatically.
set -euo pipefail

say() { echo; echo "==> $*"; }

if [ ! -e /proc/device-tree/model ] || ! grep -qi raspberry /proc/device-tree/model; then
    echo "This installer is for a Raspberry Pi (found no Pi model string)."
    echo "On a Mac, use: bash mac/run.sh"
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(whoami)}"
HOME_DIR="$(getent passwd "$RUN_USER" | cut -d: -f6)"
[ -n "$HOME_DIR" ] || HOME_DIR="$HOME"
MUSIC_DIR="$HOME_DIR/Music"
BOOT_CONFIG="/boot/firmware/config.txt"
[ -f "$BOOT_CONFIG" ] || BOOT_CONFIG="/boot/config.txt"   # pre-Bookworm layout

say "1/7  Installing system packages (mpd, mpc, python3-pip, i2c-tools, ...)"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    mpd mpc python3-pip python3-pygame python3-numpy python3-spidev \
    python3-rpi.gpio i2c-tools bluez git

say "2/7  Installing Python libraries from requirements-pi.txt"
sudo pip3 install --quiet --break-system-packages -r "$REPO_DIR/requirements-pi.txt"

say "3/7  Enabling the SPI (display) and I2C (encoder) interfaces"
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
# the web app's address is http://device.local:8080 — that name IS the hostname
if [ "$(hostname)" != "device" ]; then
    echo "    setting hostname to 'device' (was '$(hostname)') so device.local works"
    sudo raspi-config nonint do_hostname device
fi

say "4/7  Configuring MPD — your music lives in $MUSIC_DIR"
mkdir -p "$MUSIC_DIR"
if [ -f /etc/mpd.conf ] && ! grep -q "pimusicdevice" /etc/mpd.conf; then
    sudo cp /etc/mpd.conf /etc/mpd.conf.dist   # keep the distro original once
fi
sudo tee /etc/mpd.conf >/dev/null <<EOF
# pimusicdevice mpd.conf — written by install.sh (original: /etc/mpd.conf.dist)
music_directory    "$MUSIC_DIR"
playlist_directory "/var/lib/mpd/playlists"
db_file            "/var/lib/mpd/tag_cache"
state_file         "/var/lib/mpd/state"
sticker_file       "/var/lib/mpd/sticker.sql"
user               "mpd"
bind_to_address    "127.0.0.1"
auto_update        "yes"

audio_output {
    type       "alsa"
    name       "Built-in / wired"
    mixer_type "software"
}
# Bluetooth speakers: add a bluealsa/PipeWire output —
# see docs/bluetooth-audio.md in the repo.
EOF
# let the mpd user reach the music dir (Bookworm homes default to 700)
sudo usermod -a -G "$(id -gn "$RUN_USER")" mpd 2>/dev/null || true
chmod g+x "$HOME_DIR"
chmod -R g+rX "$MUSIC_DIR"
sudo systemctl enable --now mpd
mpc update >/dev/null 2>&1 || true

say "5/7  Applying power tweaks (HDMI off, ACT LED off, powersave governor)"
if ! grep -q "pimusicdevice power tweaks" "$BOOT_CONFIG"; then
    sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# pimusicdevice power tweaks (marker line — install.sh checks for it)
# ACT LED off (invisible inside a case) + HDMI powered down when unused.
dtparam=act_led_trigger=none
dtparam=act_led_activelow=on
hdmi_blanking=2
EOF
    echo "    added to $BOOT_CONFIG (takes effect after reboot)"
else
    echo "    already present in $BOOT_CONFIG"
fi
sudo cp "$REPO_DIR/systemd/pimusicdevice-powersave.service" /etc/systemd/system/
# Allow POWER_SWITCH_ACTION="shutdown" to poweroff without a password
echo "$RUN_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff, /bin/systemctl poweroff" \
    | sudo tee /etc/sudoers.d/pimusicdevice >/dev/null
sudo chmod 440 /etc/sudoers.d/pimusicdevice

say "6/7  Installing the device service (starts the UI at boot)"
sudo tee /etc/systemd/system/pimusicdevice.service >/dev/null <<EOF
[Unit]
Description=pimusicdevice — pocket music player
# NOT after network-online.target: the app manages WiFi itself and the web app
# binds without a live network, so waiting for DHCP added ~10-20s of dead time
# to every boot (see systemd/pimusicdevice.service).
After=mpd.service bluetooth.service sound.target
Wants=mpd.service
# never permanently give up restarting (see systemd/pimusicdevice.service)
StartLimitIntervalSec=0

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_DIR
ExecStartPre=+/bin/sh $REPO_DIR/pi/unblock_bluetooth.sh
ExecStart=/usr/bin/python3 $REPO_DIR/pi/device.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable pimusicdevice pimusicdevice-powersave >/dev/null

say "7/7  All set"
echo "Done — run 'sudo reboot'; the device UI starts automatically."
echo "To load music: open Settings -> Web App on the device and scan the"
echo "QR code (or browse to http://device.local:8080). Manual route:"
echo "copy files into $MUSIC_DIR and run 'mpc update'. See the README's"
echo "troubleshooting table if the screen, knob, or web app misbehaves."
