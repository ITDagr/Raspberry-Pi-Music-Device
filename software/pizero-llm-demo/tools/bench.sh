#!/usr/bin/env bash
# Measure what this board actually does — run ON THE PI.
#
# Reports prefill (pp) and generation (tg) rates, then the memory picture.
# Generation on a Zero 2 W is memory-bandwidth-bound, so tg tracks model size
# more than parameter count: a smaller quant of the same model is faster.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$HERE/config.sh"

MODEL="$MODEL_DIR/$MODEL_FILE"
[[ -f "$MODEL" ]] || { echo "model not found: $MODEL" >&2; exit 1; }

echo "=== model ==="
ls -lh "$MODEL" | awk '{print $5, $9}'

echo
echo "=== memory before ==="
free -m

echo
echo "=== llama-bench (pp=prefill, tg=generation) ==="
# Stop the server first so it isn't holding a second copy of the weights in
# page cache and competing for all four cores.
sudo systemctl stop llamad.service 2>/dev/null || true
LD_LIBRARY_PATH="$LLAMA_DIR/bin" "$LLAMA_DIR/bin/llama-bench" -m "$MODEL" -p 64 -n 32 -t "$THREADS" -r 2 || true
sudo systemctl start llamad.service 2>/dev/null || true

echo
echo "=== memory after (server reloading) ==="
free -m
echo
echo "Reading the result:"
echo "  tg t/s is what the screen shows while answering."
echo "  If tg is far below ~4 t/s, the weights are not staying resident —"
echo "  check 'free -m' Swap used, and drop to a smaller quant in config.sh."
