# Installing on the Raspberry Pi

Target: Raspberry Pi Zero 2 W, Raspberry Pi OS **Bookworm Lite** (64-bit),
Python 3.11. Wire the hardware first — see [hardware.md](hardware.md).

## 1. OS + interfaces

1. Flash Pi OS Bookworm Lite, boot, and get on Wi-Fi.
2. `sudo raspi-config` → *Interface Options* → enable **SPI** and **I2C**.
3. `sudo reboot`, then confirm: `ls /dev/spidev0.0` and `i2cdetect -y 1`
   (the ANO encoder shows at `0x49`, the DRV2605L at `0x5a`).

## 2. Software

```sh
sudo apt update
sudo apt install -y python3-pygame python3-numpy python3-spidev \
                    python3-rpi.gpio python3-pip mpd mpc bluez i2c-tools git

cd /home/pi
git clone <your-remote-or-copy> pimusicdevice
cd pimusicdevice
pip3 install --break-system-packages adafruit-blinka \
     adafruit-circuitpython-seesaw adafruit-circuitpython-drv2605 python-mpd2
```

(Or `pip3 install -r requirements-pi.txt` inside a venv with
`--system-site-packages` so apt's pygame/numpy are reused.)

## 3. Music library (MPD)

```sh
sudo systemctl enable --now mpd
# put music in MPD's music_directory (default /var/lib/mpd/music)
sudo cp -r ~/Music/* /var/lib/mpd/music/
mpc update && mpc stats
```

The device builds its library from MPD tags (artist / album / track number),
so tagged files browse best. Untagged files fall back to filenames.

## 4. First run

```sh
cd /home/pi/pimusicdevice
python3 pi/device.py
```

You should see the boot animation on the TFT and land in the menu. If the
image is shifted, colors are wrong, or the wheel scrolls backwards, see
[troubleshooting.md](troubleshooting.md) — every pin and offset lives in
`shared/config.py`, marked `# match your wiring`.

## 5. Start on boot (systemd)

```sh
sudo cp systemd/pimusicdevice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pimusicdevice
journalctl -u pimusicdevice -f        # watch logs
```

The unit runs as user `pi` from `/home/pi/pimusicdevice`, restarts on
failure, and waits for MPD.

## 6. Optional extras

- **PiSugar battery/RTC**: install the PiSugar power manager per its docs;
  the device polls `127.0.0.1:8423` automatically and degrades silently
  when it's absent.
- **Bluetooth speakers/headphones**: see
  [bluetooth-audio.md](bluetooth-audio.md) for routing MPD's output.
- Playback state persists at `/home/pi/.device_state.json`; delete it to
  reset volume/brightness/resume.
