# pizero-llm-demo — install-time configuration.
# Sourced by install.sh and tools/*.sh. Edit before installing.

# --- model ------------------------------------------------------------------
# Three vetted profiles. Sizes are real (checked against the HF API), and the
# budget is MEASURED on the actual board, not estimated:
#
#   463 MB MemTotal   (measured after gpu_mem=16; it is 415 MB before)
#  -150 MB Pi OS 13 Lite, bluetooth trimmed (measured 161 MB at idle)
#  - 65 MB Python UI (Pillow + numpy + Blinka + rpi-lgpio)
#  - 60 MB llama-server anon: process + compute buffers + KV cache @ -c 512
#  = ~190 MB of page cache left to hold mmap'd weights
#
# That is TIGHTER than the 219 MiB default model, so expect some paging on the
# first answer while the cache settles. Run tools/bench.sh and check `free -m`:
# if generation sits well under ~4 tok/s, drop a quant level or lower CTX_SIZE.
#
# SAFE (default): SmolLM2-360M-Instruct Q4_0, 219 MiB.
#   Plain Llama architecture, so every llama.cpp version supports it. Q4_0 gets
#   runtime-repacked into an ARM-friendly layout on load, which matters on the
#   A53 (no dotprod/i8mm instructions). Smallest AND fastest of the good options
#   because token generation is memory-bandwidth-bound: fewer bytes per token.
MODEL_URL="https://huggingface.co/bartowski/SmolLM2-360M-Instruct-GGUF/resolve/main/SmolLM2-360M-Instruct-Q4_0.gguf"
MODEL_FILE="SmolLM2-360M-Instruct-Q4_0.gguf"
MODEL_LABEL="SmolLM2-360M"          # shown on the stats strip
MODEL_QUANT="Q4_0"                  # shown on the stats strip
MODEL_MIN_BYTES=200000000           # sanity floor for a completed download

# BETTER QUALITY: LFM2-350M Q4_K_M, 219 MiB. Same footprint, newer model,
# scores above SmolLM2-360M on instruction following. Needs a llama.cpp new
# enough to know the `lfm2` architecture — if the server logs an unknown-arch
# error, fall back to SAFE.
# MODEL_URL="https://huggingface.co/LiquidAI/LFM2-350M-GGUF/resolve/main/LFM2-350M-Q4_K_M.gguf"
# MODEL_FILE="LFM2-350M-Q4_K_M.gguf"
# MODEL_LABEL="LFM2-350M"
# MODEL_QUANT="Q4_K_M"

# STRETCH: Qwen2.5-0.5B-Instruct Q4_0, 337 MiB — the largest parameter count
# that runs without falling off the mmap cliff. 494M params, but it leaves only
# ~30 MB of slack, so you MUST also set UI_LEAN=1 below and expect the first
# token to be slow while the page cache settles. Note the *official* Qwen GGUFs
# are all >=396 MiB (they keep the embedding tensor at f16, and with a 151k
# vocab that alone is ~272 MB) — this is bartowski's requant, which doesn't.
# MODEL_URL="https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_0.gguf"
# MODEL_FILE="Qwen2.5-0.5B-Instruct-Q4_0.gguf"
# MODEL_LABEL="Qwen2.5-0.5B"
# MODEL_QUANT="Q4_0"

# --- inference --------------------------------------------------------------
CTX_SIZE=512            # KV cache is ~40 KB/token f16 on a 32-layer 360M model:
                        # 512 ctx = ~20 MB, 2048 ctx = ~80 MB you do not have.
N_PREDICT=200           # max tokens per answer; ~12 lines is all the screen holds
THREADS=4               # all four A53 cores
KV_TYPE=q8_0            # quantize the K cache (~25% off the KV total). K only:
                        # quantizing V as well requires flash-attention, which
                        # is not a safe default on a CPU-only A53 build.

# --- llama.cpp -------------------------------------------------------------
# The project publishes prebuilt linux/arm64 binaries per build, and they work
# on this board: the archive carries several CPU backend variants including
# libggml-cpu-armv8.0_1.so and dispatches at runtime, which is exactly the A53's
# baseline (no dotprod, no i8mm). Verified on the device — no Docker, no
# cross-compile, no 3-hour on-Pi build.
#
# Pinned for reproducibility. Bump it to pick up a newer llama.cpp; set it to
# "" to force the source-build path instead.
LLAMA_RELEASE="b10930"
LLAMA_REF="master"      # only used by the source-build fallback
LLAMA_DIR=/opt/llama.cpp
LLAMA_PORT=8081

# --- paths -----------------------------------------------------------------
APP_DIR=/opt/llmdemo
MODEL_DIR=/opt/llmdemo/models
RUN_USER=pi

# --- system tuning ---------------------------------------------------------
SET_GPU_MEM=1           # gpu_mem=16 in config.txt -> frees ~48 MB (needs reboot)
TRIM_SERVICES=1         # disable bluetooth/avahi/triggerhappy/ModemManager
SWAP_MB=512             # shock absorber so the OOM killer slows us instead of
                        # reaping llama-server. Raised to 2048 automatically if
                        # install.sh has to compile llama-server on the Pi.
UI_LEAN=1               # 1 = push only changed screen regions instead of full
                        # frames. Cuts SPI traffic from ~115 KB to ~12 KB for a
                        # stats-strip tick and measurably reduces CPU stolen
                        # from inference. Recommended with the STRETCH model.
