#!/usr/bin/env python3
# AeroNode MicroPython ESP32-C3 lite trim helper
# Fix v3: when disabling MicroPython _thread, also disable MICROPY_PY_THREAD_GIL.
#
# Usage in workflow, after cloning/patching MicroPython and before build:
#   python3 scripts/aeronode_trim.py work/micropython

from __future__ import annotations

import re
import sys
from pathlib import Path


def replace_define(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^\s*#\s*define\s+{re.escape(name)}\b.*$", re.M)
    line = f"#define {name} {value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    return text.rstrip() + "\n\n// AeroNode lite overrides\n" + line + "\n"


def replace_define_if_present(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^\s*#\s*define\s+{re.escape(name)}\b.*$", re.M)
    line = f"#define {name} {value}"
    return pattern.sub(line, text, count=1)


def patch_mpconfigport(mp_root: Path) -> None:
    cfg = mp_root / "ports" / "esp32" / "mpconfigport.h"
    if not cfg.exists():
        raise FileNotFoundError(f"Cannot find {cfg}")

    text = cfg.read_text(encoding="utf-8")

    # Critical fix:
    # ESP32 port normally defines both MICROPY_PY_THREAD and MICROPY_PY_THREAD_GIL.
    # If _thread is disabled but GIL stays enabled, mpstate.h still declares
    # "mp_thread_mutex_t gil_mutex", while mp_thread_mutex_t is not available.
    text = replace_define(text, "MICROPY_PY_THREAD", "(0)")
    text = replace_define(text, "MICROPY_PY_THREAD_GIL", "(0)")

    # Keep BLE enabled, as requested.
    text = replace_define_if_present(text, "MICROPY_PY_BLUETOOTH", "(1)")

    # Low-risk savings for the weather station.
    # Do not disable MICROPY_PY_SSL here; PEAP/EAP may need IDF TLS pieces.
    text = replace_define_if_present(text, "MICROPY_PY_WEBREPL", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_WEBSOCKET", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_SOCKET_EVENTS", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_ESPNOW", "(0)")

    cfg.write_text(text, encoding="utf-8")
    print(f"[AeroNode trim] patched {cfg}")
    print("[AeroNode trim] MICROPY_PY_THREAD=0, MICROPY_PY_THREAD_GIL=0, BLE kept")


def patch_sdkconfig_defaults(mp_root: Path, board: str = "ESP32_GENERIC_C3") -> None:
    board_dir = mp_root / "ports" / "esp32" / "boards" / board
    if not board_dir.exists():
        print(f"[AeroNode trim] board dir not found, skip sdkconfig: {board_dir}")
        return

    sdk = board_dir / "sdkconfig.board"
    existing = sdk.read_text(encoding="utf-8") if sdk.exists() else ""

    block = """
# ---- AeroNode lite overrides ----
CONFIG_BT_ENABLED=y
CONFIG_BT_NIMBLE_ENABLED=y
CONFIG_BT_BLUEDROID_ENABLED=n

CONFIG_ESP_WIFI_STA_WPA2_ENT=y
CONFIG_WPA_MBEDTLS_CRYPTO=y
CONFIG_WPA_MBEDTLS_TLS_CLIENT=y

CONFIG_ESP_WIFI_SOFTAP_SUPPORT=n
"""
    marker = "# ---- AeroNode lite overrides ----"
    if marker not in existing:
        sdk.write_text(existing.rstrip() + "\n\n" + block.lstrip(), encoding="utf-8")
        print(f"[AeroNode trim] appended {sdk}")
    else:
        print(f"[AeroNode trim] sdkconfig overrides already present: {sdk}")


def main() -> int:
    if len(sys.argv) >= 2:
        mp_root = Path(sys.argv[1]).resolve()
    else:
        candidates = [Path.cwd(), Path.cwd() / "work" / "micropython"]
        mp_root = next((p.resolve() for p in candidates if (p / "ports" / "esp32").exists()), None)
        if mp_root is None:
            print("Usage: python3 scripts/aeronode_trim.py <path-to-micropython>", file=sys.stderr)
            return 2

    patch_mpconfigport(mp_root)
    patch_sdkconfig_defaults(mp_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
