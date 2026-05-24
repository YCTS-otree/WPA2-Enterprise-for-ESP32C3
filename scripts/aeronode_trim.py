#!/usr/bin/env python3
"""AeroNode Lite trim pass for MicroPython ESP32-C3 builds.

Design goal: low-risk size/RAM reduction for ESP32-C3FH4 4MB / no PSRAM while
keeping WiFi, BLE, LittleFS/VFS, sockets, NTP, and WPA2-Enterprise PEAP usable.

Important: PEAP/MSCHAPv2 uses TLS internally, so this script intentionally does
NOT remove mbedTLS/ssl. Cutting TLS here would be the classic '为了省内存把发动机拆了'。
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
if not (root / "ports" / "esp32").exists():
    raise SystemExit(f"Not a MicroPython tree: {root}")

changes: list[str] = []

def replace_define(path: Path, macro: str, value: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    old = text
    # Handles both #define X (1) and #define X 1 forms.
    pat = re.compile(rf"^\s*#\s*define\s+{re.escape(macro)}\s+.*$", re.M)
    repl = f"#define {macro} ({value})"
    if pat.search(text):
        text = pat.sub(repl, text)
    else:
        text += f"\n// AeroNode Lite override\n#ifndef {macro}\n#define {macro} ({value})\n#endif\n"
    if text != old:
        path.write_text(text, encoding="utf-8")
        changes.append(f"{path.relative_to(root)}: {macro}={value}")

mpconfig = root / "ports" / "esp32" / "mpconfigport.h"
# btree is not needed for the weather station. PR #17789 also mentions removing
# BTREE to compensate WPA2-Enterprise overhead; this is a low-risk cut.
replace_define(mpconfig, "MICROPY_PY_BTREE", "0")

# Optional aggressive cut: Python _thread module. ESP32-C3 is single-core and the
# current AeroNode loop is cooperative/timer-driven. Default ON because it saves
# heap/flash, but KEEP_THREAD=1 can undo this if a future script imports _thread.
if os.environ.get("KEEP_THREAD", "0") != "1":
    replace_define(mpconfig, "MICROPY_PY_THREAD", "0")

# WebREPL is useful on LAN but wastes flash and can leave another network service
# in a tiny RAM budget. Comment out frozen WebREPL manifest entries if present.
for manifest in [root / "ports" / "esp32" / "boards" / "manifest.py"]:
    if not manifest.exists():
        continue
    text = manifest.read_text(encoding="utf-8", errors="ignore")
    old = text
    lines = []
    for line in text.splitlines():
        if "webrepl" in line.lower() and not line.lstrip().startswith("#"):
            lines.append("# AeroNode Lite removed: " + line)
            changes.append(f"{manifest.relative_to(root)}: removed WebREPL frozen entry")
        else:
            lines.append(line)
    text = "\n".join(lines) + "\n"
    if text != old:
        manifest.write_text(text, encoding="utf-8")

print("[INFO] AeroNode Lite changes:")
if changes:
    for c in changes:
        print("  -", c)
else:
    print("  - no matching optional features found; continuing")
