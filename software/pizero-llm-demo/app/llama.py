"""pizero-llm-demo — streaming client for llama-server.

Why a separate server process instead of calling llama-cli per prompt:

  * llama-cli's flags churn between releases; /completion's JSON body does not
  * the model stays mmap'd and warm between prompts, so only the first answer
    pays the page-in cost
  * if inference crashes or gets OOM-killed, the UI survives and can say so

Only stdlib HTTP here — `requests` would add a dependency and resident memory
for one POST.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from app import config


class LlamaError(RuntimeError):
    pass


class LlamaClient:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._base = f"http://{host or config.LLAMA_HOST}:{port or config.LLAMA_PORT}"

    # --- status -------------------------------------------------------------
    def healthy(self) -> bool:
        """True once the model is loaded and the server will accept work."""
        try:
            with urllib.request.urlopen(f"{self._base}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    # --- generation ---------------------------------------------------------
    def stream(self, user_prompt: str, on_token, should_stop,
               n_predict: int | None = None) -> dict:
        """Generate, calling on_token(str) per chunk. Blocking — run me in a
        thread. Returns the final server payload (which carries `timings`).

        should_stop() is polled between chunks; returning True closes the
        connection, and llama-server cancels the completion when its client
        disconnects.
        """
        body = {
            "prompt": config.PROMPT_TEMPLATE.format(
                system=config.SYSTEM_PROMPT, user=user_prompt),
            "n_predict": n_predict or config.N_PREDICT,
            "temperature": config.TEMPERATURE,
            "top_p": config.TOP_P,
            "stop": config.STOP,
            "stream": True,
            "cache_prompt": True,   # the system prefix is identical every time
        }
        req = urllib.request.Request(
            f"{self._base}/completion",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        final: dict = {}
        try:
            # Generous: on this board prefill alone can take ~10-20 s before
            # the first chunk arrives.
            with urllib.request.urlopen(req, timeout=180) as resp:
                for raw in resp:
                    if should_stop():
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        chunk = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    text = chunk.get("content") or ""
                    if text:
                        on_token(text)
                    if chunk.get("stop"):
                        final = chunk
                        break
        except urllib.error.URLError as exc:
            raise LlamaError(f"inference backend unreachable: {exc.reason}") from exc
        except socket.timeout as exc:
            raise LlamaError("inference timed out") from exc
        except Exception as exc:
            raise LlamaError(str(exc)) from exc
        return final

    @staticmethod
    def tokens_per_second(final: dict) -> float | None:
        """Server-measured generation rate, if the final payload carried it."""
        t = (final or {}).get("timings") or {}
        val = t.get("predicted_per_second")
        try:
            return float(val) if val else None
        except (TypeError, ValueError):
            return None
