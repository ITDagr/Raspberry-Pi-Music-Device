#!/bin/sh
# device v2 — some images bring the Bluetooth adapter up rfkill soft-blocked
# regardless of country config; clear it before the app starts. Run as root
# via the service's `ExecStartPre=+` (the app itself still runs as `pi`).
for f in /sys/class/rfkill/*/; do
    if [ "$(cat "${f}type" 2>/dev/null)" = "bluetooth" ]; then
        echo 0 > "${f}soft" || true
    fi
done
