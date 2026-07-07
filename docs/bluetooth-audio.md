# Bluetooth audio — pairing and routing MPD

The device's Bluetooth screen handles **discovery, pairing, and
connecting** (it drives `bluetoothctl`). Routing MPD's *audio* to the
connected sink is system configuration — one of the two setups below.

## First: verify the connection layer

```sh
bluetoothctl power on
bluetoothctl --timeout 6 scan on
bluetoothctl devices            # your speaker should be listed
```

On the device: Settings → Bluetooth → select the sink. `bluetoothctl info
<MAC>` should show `Connected: yes` (the same check the UI polls).

## Option A — PipeWire (Bookworm default)

1. Install Bluetooth audio support:

   ```sh
   sudo apt install -y pipewire pipewire-audio libspa-0.2-bluetooth
   systemctl --user restart pipewire wireplumber
   ```

2. Point MPD at PulseAudio-compatible output. In `/etc/mpd.conf`:

   ```
   audio_output {
       type   "pulse"
       name   "PipeWire"
   }
   ```

   `sudo systemctl restart mpd`

3. After the device connects the sink, make it the default:

   ```sh
   wpctl status                   # find the bluez sink id
   wpctl set-default <id>
   ```

   WirePlumber remembers the default per device, so subsequent connects
   route automatically.

Note: MPD runs as its own user; give it a PipeWire session by running MPD
as your login user (user service) or configure a system-wide PipeWire —
the simplest reliable route on a headless Pi is Option B.

## Option B — bluealsa (lean, headless-friendly)

1. ```sh
   sudo apt install -y bluez-alsa-utils
   ```

2. Add a bluealsa output to `/etc/mpd.conf` (one per speaker MAC):

   ```
   audio_output {
       type    "alsa"
       name    "BT speaker"
       device  "bluealsa:DEV=XX:XX:XX:XX:XX:XX,PROFILE=a2dp"
       mixer_type "software"
   }
   ```

3. ```sh
   sudo systemctl restart mpd
   mpc outputs                     # note the output number
   mpc enable 2                    # enable the BT output (example)
   mpc disable 1                   # optionally silence the built-in output
   ```

## Tips

- Volume on the device drives MPD's `setvol` (software mixer), so it works
  the same over Bluetooth and wired audio.
- If audio stutters on a Pi Zero 2 W, prefer SBC over AAC codecs and keep
  the sink close; A2DP + 62.5 MHz SPI redraws share one small CPU.
- The UI treats a device as connected once `bluetoothctl` reports it (or
  4 s pass) — if audio doesn't follow, the routing layer (this page) is
  the part to debug, not the UI.
