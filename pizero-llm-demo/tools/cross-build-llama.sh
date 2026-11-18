#!/usr/bin/env bash
# Cross-build llama.cpp for the Pi Zero 2 W — run this ON YOUR MAC.
#
# Why: compiling llama-server on the Pi itself takes 2-4 hours and thrashes
# swap, because server.cpp pulls in cpp-httplib + nlohmann/json and that single
# translation unit wants well over 1 GB of RAM. On Apple Silicon a linux/arm64
# container runs natively, so the same build finishes in minutes.
#
# Two flags matter and both are easy to get wrong:
#   -mcpu=cortex-a53      the A53 is ARMv8.0 with no dotprod/i8mm; an Apple
#                         Silicon host defaults to a much newer baseline and
#                         the resulting binary dies with SIGILL on the Pi
#   -DGGML_NATIVE=OFF     otherwise ggml probes the *build* machine's CPU
#
# Debian bookworm base matches Raspberry Pi OS Bookworm's glibc, and static
# linking means the tarball is three self-contained binaries.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$HERE/config.sh"

OUT="$HERE/prebuilt"
mkdir -p "$OUT"

command -v docker >/dev/null || {
  echo "docker not found. Install Docker Desktop, or build on another arm64 Linux host." >&2
  exit 1
}

echo "==> building llama.cpp ($LLAMA_REF) for linux/arm64, target cortex-a53"
docker run --rm --platform linux/arm64 \
  -v "$OUT":/out \
  -e LLAMA_REF="$LLAMA_REF" \
  debian:bookworm bash -euxc '
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends \
      build-essential cmake git ca-certificates
    git clone --depth 1 --branch "$LLAMA_REF" \
      https://github.com/ggml-org/llama.cpp /src
    cmake -S /src -B /build \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=OFF \
      -DGGML_NATIVE=OFF \
      -DCMAKE_C_FLAGS="-mcpu=cortex-a53" \
      -DCMAKE_CXX_FLAGS="-mcpu=cortex-a53"
    cmake --build /build -j"$(nproc)" \
      --target llama-server llama-cli llama-bench
    cd /build/bin
    strip llama-server llama-cli llama-bench
    tar czf /out/llama-arm64.tar.gz llama-server llama-cli llama-bench
  '

echo
echo "==> $OUT/llama-arm64.tar.gz  ($(du -h "$OUT/llama-arm64.tar.gz" | cut -f1))"
echo
echo "Copy the whole repo to the Pi and install. Use tar over ssh rather than"
echo "scp of individual files — it cannot silently drop files into the wrong"
echo "directory the way a scp directory target can:"
echo
echo "    tar czf - --exclude .git . | ssh pi@<host> 'mkdir -p ~/pizero-llm-demo && tar xzf - -C ~/pizero-llm-demo'"
echo "    ssh pi@<host> 'cd ~/pizero-llm-demo && ./install.sh'"
