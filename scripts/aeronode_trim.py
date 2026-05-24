#!/usr/bin/env python3
# AeroNode MicroPython ESP32-C3 lite trim helper
# Fix v5: BLE disabled, plus ESP-IDF v5.4 EAP-method compatibility shim.
#
# Usage in workflow, after cloning/patching MicroPython and before build:
#   python3 scripts/aeronode_trim.py work/micropython

from __future__ import annotations

import re
import sys
from pathlib import Path


def replace_define(text: str, name: str, value: str) -> str:
    """Replace a C #define. If it does not exist, append it."""
    pattern = re.compile(rf"^\s*#\s*define\s+{re.escape(name)}\b.*$", re.M)
    line = f"#define {name} {value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    return text.rstrip() + "\n\n// AeroNode lite overrides\n" + line + "\n"


def replace_define_if_present(text: str, name: str, value: str) -> str:
    """Replace a C #define only when it already exists."""
    pattern = re.compile(rf"^\s*#\s*define\s+{re.escape(name)}\b.*$", re.M)
    line = f"#define {name} {value}"
    return pattern.sub(line, text, count=1)


def set_sdkconfig_key(text: str, key: str, value: str) -> str:
    """Set CONFIG_FOO=y/n in sdkconfig-style text, replacing existing lines."""
    pattern = re.compile(rf"^\s*{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    return text.rstrip() + "\n" + line + "\n"


def patch_mpconfigport(mp_root: Path) -> None:
    cfg = mp_root / "ports" / "esp32" / "mpconfigport.h"
    if not cfg.exists():
        raise FileNotFoundError(f"Cannot find {cfg}")

    text = cfg.read_text(encoding="utf-8")

    # Disable MicroPython thread support.
    # Important: _thread and GIL must be disabled together.
    # Otherwise mpstate.h may still declare mp_thread_mutex_t gil_mutex.
    text = replace_define(text, "MICROPY_PY_THREAD", "(0)")
    text = replace_define(text, "MICROPY_PY_THREAD_GIL", "(0)")

    # Disable BLE/Bluetooth at MicroPython level.
    # This avoids extmod/modbluetooth.c requiring mp_thread_* helpers.
    text = replace_define(text, "MICROPY_PY_BLUETOOTH", "(0)")
    text = replace_define_if_present(text, "MICROPY_BLUETOOTH_NIMBLE", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_BLUETOOTH_ENABLE_L2CAP_CHANNELS", "(0)")

    # Low-risk savings for the weather station.
    # Do not disable MICROPY_PY_SSL here; PEAP/EAP may need IDF TLS pieces.
    text = replace_define_if_present(text, "MICROPY_PY_WEBREPL", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_WEBSOCKET", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_SOCKET_EVENTS", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_ESPNOW", "(0)")

    cfg.write_text(text, encoding="utf-8")
    print(f"[AeroNode trim] patched {cfg}")
    print("[AeroNode trim] THREAD=0, GIL=0, BLUETOOTH=0")


def patch_sdkconfig_defaults(mp_root: Path, board: str = "ESP32_GENERIC_C3") -> None:
    board_dir = mp_root / "ports" / "esp32" / "boards" / board
    if not board_dir.exists():
        print(f"[AeroNode trim] board dir not found, skip sdkconfig: {board_dir}")
        return

    sdk = board_dir / "sdkconfig.board"
    text = sdk.read_text(encoding="utf-8") if sdk.exists() else ""

    # Disable Bluetooth/BLE at ESP-IDF level.
    text = set_sdkconfig_key(text, "CONFIG_BT_ENABLED", "n")
    text = set_sdkconfig_key(text, "CONFIG_BT_NIMBLE_ENABLED", "n")
    text = set_sdkconfig_key(text, "CONFIG_BT_BLUEDROID_ENABLED", "n")

    # Keep Enterprise Wi-Fi / PEAP-related pieces.
    text = set_sdkconfig_key(text, "CONFIG_ESP_WIFI_STA_WPA2_ENT", "y")
    text = set_sdkconfig_key(text, "CONFIG_WPA_MBEDTLS_CRYPTO", "y")
    text = set_sdkconfig_key(text, "CONFIG_WPA_MBEDTLS_TLS_CLIENT", "y")

    # Weather station does not need AP mode.
    text = set_sdkconfig_key(text, "CONFIG_ESP_WIFI_SOFTAP_SUPPORT", "n")

    sdk.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"[AeroNode trim] patched {sdk}")
    print("[AeroNode trim] ESP-IDF Bluetooth disabled; WPA2-Enterprise kept")


def patch_network_wlan_eap_methods_compat(mp_root: Path) -> None:
    """Patch network_wlan.c so PR #17234 builds on ESP-IDF v5.4.x.

    PR #17234 uses esp_eap_client_set_eap_methods() and ESP_EAP_TYPE_*.
    These are present in newer ESP-IDF, but not in v5.4.x. For v5.4.x we
    safely turn the optional method filter into a no-op. Espressif documents
    that when set_eap_methods() is not called, all supported EAP methods are
    considered, which is exactly what we want for PEAP/MSCHAPv2 school Wi-Fi.
    """
    nw = mp_root / "ports" / "esp32" / "network_wlan.c"
    if not nw.exists():
        raise FileNotFoundError(f"Cannot find {nw}")

    text = nw.read_text(encoding="utf-8")

    if "AERONODE_IDF54_EAP_METHODS_COMPAT" in text:
        print(f"[AeroNode trim] EAP-method compat already present in {nw}")
        return

    # Make sure ESP_IDF_VERSION / ESP_IDF_VERSION_VAL are available.
    if '#include "esp_idf_version.h"' not in text:
        text = re.sub(
            r'(#include\s+"esp_event\.h"\s*\n)',
            r'\1#include "esp_idf_version.h"\n',
            text,
            count=1,
        )
        if '#include "esp_idf_version.h"' not in text:
            text = '#include "esp_idf_version.h"\n' + text

    shim = '''

// AeroNode: ESP-IDF v5.4.x compatibility for MicroPython WPA2-Enterprise PR #17234.
// esp_eap_client_set_eap_methods() and ESP_EAP_TYPE_* were added after v5.4.x.
// On v5.4.x, leaving the method filter unset means "try all supported EAP methods".
#ifndef AERONODE_IDF54_EAP_METHODS_COMPAT
#define AERONODE_IDF54_EAP_METHODS_COMPAT (1)
#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 5, 0)
#define ESP_EAP_TYPE_ALL  (0)
#define ESP_EAP_TYPE_PEAP (0)
#define ESP_EAP_TYPE_TTLS (0)
#define ESP_EAP_TYPE_TLS  (0)
#define esp_eap_client_set_eap_methods(methods) (ESP_OK)
#endif
#endif
'''

    # Put the shim right after esp_eap_client.h if present, otherwise after includes.
    if '#include "esp_eap_client.h"' in text:
        text = text.replace('#include "esp_eap_client.h"', '#include "esp_eap_client.h"' + shim, 1)
    else:
        matches = list(re.finditer(r'^#include\s+[<"].*[>"]\s*$', text, flags=re.M))
        if matches:
            pos = matches[-1].end()
            text = text[:pos] + shim + text[pos:]
        else:
            text = shim + text

    nw.write_text(text, encoding="utf-8")
    print(f"[AeroNode trim] patched {nw}")
    print("[AeroNode trim] IDF<5.5 EAP-method filter converted to no-op")


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
    patch_network_wlan_eap_methods_compat(mp_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
