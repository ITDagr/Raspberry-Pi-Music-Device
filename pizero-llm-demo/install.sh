#!/usr/bin/env bash
# pizero-llm-demo — installer. Run ON THE PI, as the normal user (needs sudo).
#
#   ./install.sh              full install
#   ./install.sh --no-model   skip the ~220 MB download (model already present)
#   ./install.sh --app-only   reinstall just the Python app + units (fast loop)
#
# Idempotent: safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/config.sh"

DO_MODEL=1; APP_ONLY=0
for a in "$@"; do case "$a" in
  --no-model) DO_MODEL=0 ;;
  --app-only) APP_ONLY=1; DO_MODEL=0 ;;
  -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
  *) echo "unknown option: $a" >&2; exit 2 ;;
esac; done

c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
step() { printf '\n%s==>%s %s\n' "$c_ok" "$c_off" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$c_warn" "$c_off" "$*"; }
die()  { printf '%s[fail]%s %s\n' "$c_err" "$c_off" "$*" >&2; exit 1; }
note() { printf '%s      %s%s\n' "$c_dim" "$*" "$c_off"; }

REBOOT_NEEDED=0

# --------------------------------------------------------------------------
step "Preflight"

[[ $EUID -ne 0 ]] || die "run as your normal user, not root (the script calls sudo itself)"
# `sudo -n true`, not `sudo -v`: -v refreshes the timestamp and prompts for a
# password even under NOPASSWD, which breaks a non-interactive ssh install.
if ! sudo -n true 2>/dev/null; then
  die "sudo needs a password here, so this cannot run non-interactively.
      Either run it from an interactive shell on the Pi, or grant NOPASSWD:
        echo \"\$USER ALL=(ALL) NOPASSWD: ALL\" | sudo tee /etc/sudoers.d/010-\$USER"
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" ]]; then
  die "arch is $ARCH, not aarch64.
      A 32-bit userland costs you a large fraction of inference throughput on
      this board. Reflash with the 64-bit Raspberry Pi OS Lite image."
fi
note "arch aarch64 ok"

MEM_TOTAL_MB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
note "MemTotal ${MEM_TOTAL_MB} MB"
if [[ $MEM_TOTAL_MB -gt 700 ]]; then
  warn "more than 512 MB detected — you have more headroom than config.sh assumes;"
  warn "consider a larger model (see the STRETCH profile and beyond)."
fi

DISK_FREE_MB=$(( $(df -Pk / | awk 'NR==2{print $4}') / 1024 ))
[[ $DISK_FREE_MB -gt 2500 ]] || die "only ${DISK_FREE_MB} MB free on / — need ~2.5 GB"
note "disk free ${DISK_FREE_MB} MB ok"

# Bookworm moved the firmware config; support both locations.
BOOTCFG=/boot/firmware/config.txt
[[ -f "$BOOTCFG" ]] || BOOTCFG=/boot/config.txt
[[ -f "$BOOTCFG" ]] || die "cannot find config.txt in /boot/firmware or /boot"
note "firmware config at $BOOTCFG"

# --------------------------------------------------------------------------
if [[ $APP_ONLY -eq 0 ]]; then
step "Packages"
sudo apt-get update -qq
# Prefer apt over pip for anything with a C extension: these all ship prebuilt
# for this exact Python, and building numpy or Pillow on a Zero 2 W is an hour
# you do not need to spend.
#
# python3-rpi-lgpio, NOT python3-rpi.gpio: Raspberry Pi OS 13 (trixie) runs a
# 6.x kernel where classic RPi.GPIO is deprecated. rpi-lgpio provides the same
# `RPi.GPIO` module name backed by lgpio, so app/display.py is unchanged.
# The two packages conflict — never install both.
#
# fonts-dejavu-core is NOT in the Lite image and the UI needs a real TTF.
sudo apt-get install -y -qq --no-install-recommends \
  python3 python3-venv python3-dev \
  python3-numpy python3-pil python3-spidev python3-rpi-lgpio \
  fonts-dejavu-core curl ca-certificates git \
  i2c-tools libgomp1
note "base packages installed"

# --------------------------------------------------------------------------
step "Buses (SPI for the panel, I2C for the encoder + haptics)"
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_spi 0 || warn "could not enable SPI via raspi-config"
  sudo raspi-config nonint do_i2c 0 || warn "could not enable I2C via raspi-config"
  note "SPI + I2C enabled"
else
  warn "raspi-config missing — ensure dtparam=spi=on and dtparam=i2c_arm=on by hand"
fi
# The UI process needs the panel (SPI), the encoder/haptics (I2C) and the
# backlight PWM (GPIO). On a stock image `pi` already has these.
sudo usermod -aG spi,gpio,i2c "${RUN_USER:-$USER}" 2>/dev/null \
  && note "added ${RUN_USER:-$USER} to spi, gpio, i2c" || true

# --------------------------------------------------------------------------
step "Reclaiming RAM"

if [[ "${SET_GPU_MEM}" == "1" ]]; then
  if grep -qE '^\s*gpu_mem=' "$BOOTCFG"; then
    cur=$(grep -oE '^\s*gpu_mem=[0-9]+' "$BOOTCFG" | tail -1 | cut -d= -f2)
    if [[ "$cur" != "16" ]]; then
      sudo sed -i 's/^\s*gpu_mem=.*/gpu_mem=16/' "$BOOTCFG"
      REBOOT_NEEDED=1; note "gpu_mem ${cur} -> 16 (frees ~48 MB after reboot)"
    else
      note "gpu_mem already 16"
    fi
  else
    echo 'gpu_mem=16' | sudo tee -a "$BOOTCFG" >/dev/null
    REBOOT_NEEDED=1; note "gpu_mem=16 appended (frees ~48 MB after reboot)"
  fi
fi

if [[ "${TRIM_SERVICES}" == "1" ]]; then
  # Bluetooth, hotplug-key daemons and a cell modem are all dead weight here.
  # avahi-daemon is deliberately NOT in this list: killing it costs you
  # `<hostname>.local` resolution, and on a headless box with a DHCP lease that
  # can move, losing mDNS discovery is a far worse trade than ~5 MB.
  for svc in bluetooth hciuart triggerhappy ModemManager; do
    if systemctl list-unit-files "${svc}.service" >/dev/null 2>&1 \
       && systemctl is-enabled "${svc}.service" >/dev/null 2>&1; then
      sudo systemctl disable --now "${svc}.service" >/dev/null 2>&1 || true
      note "disabled ${svc}"
    fi
  done
fi

# Keep the journal in RAM and small, instead of growing on the SD card.
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/10-llmdemo.conf >/dev/null <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=16M
EOF
sudo systemctl restart systemd-journald || true
note "journald -> volatile, capped at 16M"

# --------------------------------------------------------------------------
step "Swap"
# This is a shock absorber, not performance. With the model sitting near the
# RAM ceiling, the OOM killer would otherwise reap llama-server outright; a
# little swap converts that into a slowdown you can see and tune.
NEED_SWAP_MB="$SWAP_MB"
PREBUILT="$HERE/prebuilt/llama-arm64.tar.gz"
if [[ ! -f "$PREBUILT" ]] && [[ -z "${LLAMA_RELEASE:-}" ]] \
   && [[ ! -x "$LLAMA_DIR/bin/llama-server" ]]; then
  # Only the source-build path needs this. Compiling llama-server's
  # cpp-httplib + nlohmann/json translation unit wants well over 1 GB of RAM
  # for a single g++ invocation, and on 512 MB that only completes by swapping
  # hard. zram cannot help — it adds no capacity, it trades RAM for RAM.
  NEED_SWAP_MB=2048
fi
# Raspberry Pi OS 13 ships zram swap and no dphys-swapfile. Note zram buys us
# nothing for this workload: mmap'd model weights are clean file-backed pages
# that get dropped from page cache, never swapped. It only matters if we have
# to compile on-device.
# swapon/i2cdetect live in /usr/sbin, which is not on the pi user's PATH.
EXISTING_SWAP_MB=$(/usr/sbin/swapon --show=SIZE --bytes --noheadings 2>/dev/null \
  | awk '{s+=$1} END {print int(s/1048576)}')
EXISTING_SWAP_MB=${EXISTING_SWAP_MB:-0}
note "existing swap: ${EXISTING_SWAP_MB} MB"

if [[ $EXISTING_SWAP_MB -ge $NEED_SWAP_MB ]]; then
  note "sufficient — leaving swap alone"
elif [[ -f /etc/dphys-swapfile ]]; then
  cur_swap=$(grep -oE '^\s*CONF_SWAPSIZE=[0-9]+' /etc/dphys-swapfile | tail -1 | cut -d= -f2 || echo 0)
  if [[ "${cur_swap:-0}" -lt "$NEED_SWAP_MB" ]]; then
    sudo sed -i "s/^\s*CONF_SWAPSIZE=.*/CONF_SWAPSIZE=${NEED_SWAP_MB}/" /etc/dphys-swapfile
    sudo dphys-swapfile swapoff 2>/dev/null || true
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
    note "swap ${cur_swap:-0} -> ${NEED_SWAP_MB} MB"
  else
    note "swap already ${cur_swap} MB"
  fi
else
  warn "dphys-swapfile not present — skipping swap setup"
fi
# Prefer evicting page cache over swapping anonymous pages; the mmap'd weights
# are clean pages that are cheap to drop and re-read.
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/60-llmdemo.conf >/dev/null
sudo sysctl -q -w vm.swappiness=10 || true

# --------------------------------------------------------------------------
step "llama.cpp"
if [[ -f "$PREBUILT" ]]; then
  note "using locally cross-built $PREBUILT"
  sudo mkdir -p "$LLAMA_DIR/bin"
  sudo tar xzf "$PREBUILT" -C "$LLAMA_DIR/bin" --strip-components=0
  note "installed prebuilt binaries to $LLAMA_DIR/bin"
elif [[ -n "${LLAMA_RELEASE:-}" ]] && [[ ! -x "$LLAMA_DIR/bin/llama-server" ]]; then
  # Official prebuilt. Shared libs and binaries land flat in bin/, and the
  # systemd unit sets LD_LIBRARY_PATH to match.
  url="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_RELEASE}/llama-${LLAMA_RELEASE}-bin-ubuntu-arm64.tar.gz"
  note "downloading prebuilt ${LLAMA_RELEASE} (linux/arm64)"
  tmp=$(mktemp -d)
  curl -fL --progress-bar -o "$tmp/ll.tar.gz" "$url" \
    || die "download failed. Bump or clear LLAMA_RELEASE in config.sh — old
      builds are pruned from GitHub releases after a while."
  sudo mkdir -p "$LLAMA_DIR/bin"
  sudo tar xzf "$tmp/ll.tar.gz" -C "$LLAMA_DIR/bin" --strip-components=1
  sudo chmod +x "$LLAMA_DIR"/bin/llama-* 2>/dev/null || true
  rm -rf "$tmp"
  note "installed ${LLAMA_RELEASE} to $LLAMA_DIR/bin"
elif [[ -x "$LLAMA_DIR/bin/llama-server" ]]; then
  note "llama-server already installed at $LLAMA_DIR/bin — skipping build"
  note "delete that directory to force a rebuild"
else
  warn "No prebuilt binaries found, and none installed."
  warn "Compiling llama-server on a Pi Zero 2 W takes 2-4 HOURS and thrashes swap."
  warn ""
  warn "The fast path is to cross-compile on your Mac instead (minutes, native"
  warn "speed on Apple Silicon) and copy the result over:"
  warn ""
  warn "    # on the Mac, in this repo"
  warn "    ./tools/cross-build-llama.sh"
  warn "    tar czf - prebuilt | ssh pi@<host> 'cd ~/pizero-llm-demo && tar xzf -'"
  warn "    # then re-run ./install.sh on the Pi"
  warn ""
  read -r -p "Compile on the Pi anyway? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || die "stopping. Cross-compile, then re-run."

  sudo apt-get install -y -qq --no-install-recommends build-essential cmake
  sudo mkdir -p "$LLAMA_DIR"
  sudo chown "$USER" "$LLAMA_DIR"
  if [[ -d "$LLAMA_DIR/src/.git" ]]; then
    git -C "$LLAMA_DIR/src" fetch --depth 1 origin "$LLAMA_REF"
    git -C "$LLAMA_DIR/src" checkout -q FETCH_HEAD
  else
    git clone --depth 1 --branch "$LLAMA_REF" \
      https://github.com/ggml-org/llama.cpp "$LLAMA_DIR/src"
  fi
  # -j1: a parallel build of server.cpp will OOM even with 2 GB of swap.
  cmake -S "$LLAMA_DIR/src" -B "$LLAMA_DIR/src/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_NATIVE=ON
  cmake --build "$LLAMA_DIR/src/build" -j1 \
    --target llama-server llama-cli llama-bench
  sudo mkdir -p "$LLAMA_DIR/bin"
  sudo install -m755 "$LLAMA_DIR/src/build/bin/llama-server" \
                     "$LLAMA_DIR/src/build/bin/llama-cli" \
                     "$LLAMA_DIR/src/build/bin/llama-bench" "$LLAMA_DIR/bin/"
  note "built and installed"
fi
[[ -x "$LLAMA_DIR/bin/llama-server" ]] || die "llama-server missing after install step"

# Catch a cross-compile that targeted the wrong CPU before systemd does.
# 132 == 128 + SIGILL(4): the binary used instructions this A53 lacks.
set +e
LD_LIBRARY_PATH="$LLAMA_DIR/bin" "$LLAMA_DIR/bin/llama-server" --help >/dev/null 2>&1
probe_rc=$?
set -e
if [[ $probe_rc -eq 132 ]]; then
  die "llama-server dies with SIGILL on this CPU.
      Rebuild with -mcpu=cortex-a53 and -DGGML_NATIVE=OFF. An Apple Silicon
      host targets a far newer ARM baseline than the A53 by default, and
      tools/cross-build-llama.sh sets both flags for exactly this reason."
fi
note "llama-server binary runs on this CPU"
fi  # end APP_ONLY guard

# --------------------------------------------------------------------------
step "Model"
sudo mkdir -p "$MODEL_DIR"
# Own the tree as the installing user so the download and venv need no sudo;
# handed to RUN_USER at the end.
sudo chown -R "$USER" "$APP_DIR"
TARGET="$MODEL_DIR/$MODEL_FILE"
if [[ $DO_MODEL -eq 1 ]]; then
  if [[ -f "$TARGET" ]] && [[ $(stat -c%s "$TARGET") -ge $MODEL_MIN_BYTES ]]; then
    note "already present: $MODEL_FILE ($(( $(stat -c%s "$TARGET") / 1048576 )) MiB)"
  else
    note "downloading $MODEL_FILE"
    # -C - resumes a partial file, which matters on flaky wifi.
    curl -fL --progress-bar -C - -o "$TARGET" "$MODEL_URL" \
      || die "download failed — check MODEL_URL in config.sh"
    sz=$(stat -c%s "$TARGET")
    [[ $sz -ge $MODEL_MIN_BYTES ]] \
      || die "downloaded file is only $sz bytes — truncated or an HTML error page"
    note "got $(( sz / 1048576 )) MiB"
  fi
else
  [[ -f "$TARGET" ]] || die "--no-model given but $TARGET is missing"
  note "using existing $MODEL_FILE"
fi

# --------------------------------------------------------------------------
step "Application"
# cp, not rsync — rsync is not guaranteed on the Lite image.
rm -rf "$APP_DIR/app"
cp -a "$HERE/app" "$APP_DIR/app"
cp -a "$HERE/requirements.txt" "$APP_DIR/requirements.txt"
note "app files copied to $APP_DIR"

if [[ ! -d "$APP_DIR/.venv" ]]; then
  # --system-site-packages so the venv sees the apt-installed numpy, Pillow,
  # spidev and the rpi-lgpio RPi.GPIO shim rather than rebuilding them.
  python3 -m venv --system-site-packages "$APP_DIR/.venv"
  note "venv created (with system site-packages)"
fi
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" \
  || die "pip install failed"
note "python deps installed"

# Generated, not templated, so every tunable lives in exactly one place:
# config.sh. The app reads this at startup.
tee "$APP_DIR/app/runtime.json" >/dev/null <<EOF
{
  "model_path":  "$TARGET",
  "model_label": "$MODEL_LABEL",
  "model_quant": "$MODEL_QUANT",
  "llama_host":  "127.0.0.1",
  "llama_port":  $LLAMA_PORT,
  "n_predict":   $N_PREDICT,
  "ctx_size":    $CTX_SIZE,
  "ui_lean":     ${UI_LEAN}
}
EOF
note "runtime.json written"

RUN_USER="${RUN_USER:-$USER}"
id "$RUN_USER" >/dev/null 2>&1 || die "RUN_USER '$RUN_USER' does not exist on this system"
if [[ "$RUN_USER" != "$USER" ]]; then
  sudo chown -R "$RUN_USER" "$APP_DIR"
  note "ownership handed to $RUN_USER"
fi

# --------------------------------------------------------------------------
step "Services"
render_unit() {
  sed -e "s|@LLAMA_DIR@|$LLAMA_DIR|g" -e "s|@APP_DIR@|$APP_DIR|g" \
      -e "s|@MODEL@|$TARGET|g"        -e "s|@PORT@|$LLAMA_PORT|g" \
      -e "s|@CTX@|$CTX_SIZE|g"        -e "s|@THREADS@|$THREADS|g" \
      -e "s|@KV@|$KV_TYPE|g"          -e "s|@USER@|$RUN_USER|g" "$1"
}
render_unit "$HERE/systemd/llamad.service"  | sudo tee /etc/systemd/system/llamad.service  >/dev/null
render_unit "$HERE/systemd/llmdemo.service" | sudo tee /etc/systemd/system/llmdemo.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable llamad.service llmdemo.service >/dev/null
note "units installed and enabled"

if [[ $REBOOT_NEEDED -eq 1 ]]; then
  warn "config.txt changed (gpu_mem) — the extra 48 MB only appears after a reboot."
  warn "Reboot before judging whether the model fits:  sudo reboot"
else
  step "Starting"
  sudo systemctl restart llamad.service
  note "waiting for the model to load (mmap from SD, give it a minute)"
  for i in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:${LLAMA_PORT}/health" >/dev/null 2>&1; then
      note "llama-server healthy after ${i}s"; break
    fi
    sleep 1
    [[ $i -lt 90 ]] || warn "still not healthy — check: journalctl -u llamad -n 40"
  done
  sudo systemctl restart llmdemo.service
fi

cat <<EOF

$(printf '%s' "$c_ok")Installed.$(printf '%s' "$c_off")

  model     $MODEL_LABEL $MODEL_QUANT  ($(( $(stat -c%s "$TARGET") / 1048576 )) MiB)
  context   $CTX_SIZE tokens, KV cache $KV_TYPE
  services  llamad.service (inference)  llmdemo.service (screen + encoder)

  logs      journalctl -u llamad -f
            journalctl -u llmdemo -f
  restart   sudo systemctl restart llmdemo
  bench     $LLAMA_DIR/bin/llama-bench -m $TARGET -p 64 -n 32 -t $THREADS
  free RAM  free -m

$(printf '%s' "$c_dim")If the screen stays black: check that 0x49 shows up in \`i2cdetect -y 1\`,
then \`journalctl -u llmdemo -n 50\`. Per your own notes, a marginal STEMMA QT
connection is the usual culprit.$(printf '%s' "$c_off")
EOF
