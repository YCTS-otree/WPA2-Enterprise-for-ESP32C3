#!/usr/bin/env python3
# AeroNode MicroPython ESP32-C3 lite trim helper
# Fix v6: BLE disabled, IDF v5.4 EAP shim, and PEAP/TTLS ca_cert optional.
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
    return pattern.sub(f"#define {name} {value}", text, count=1)


def set_sdkconfig_key(text: str, key: str, value: str) -> str:
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

    # Disable MicroPython thread support; _thread and GIL must be disabled together.
    text = replace_define(text, "MICROPY_PY_THREAD", "(0)")
    text = replace_define(text, "MICROPY_PY_THREAD_GIL", "(0)")

    # Disable BLE/Bluetooth at MicroPython level.
    text = replace_define(text, "MICROPY_PY_BLUETOOTH", "(0)")
    text = replace_define_if_present(text, "MICROPY_BLUETOOTH_NIMBLE", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE", "(0)")
    text = replace_define_if_present(text, "MICROPY_PY_BLUETOOTH_ENABLE_L2CAP_CHANNELS", "(0)")

    # Low-risk savings for the weather station. Do not disable SSL/TLS.
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
    """Patch network_wlan.c so PR #17234 builds on ESP-IDF v5.4.x."""
    nw = mp_root / "ports" / "esp32" / "network_wlan.c"
    if not nw.exists():
        raise FileNotFoundError(f"Cannot find {nw}")

    text = nw.read_text(encoding="utf-8")
    if "AERONODE_IDF54_EAP_METHODS_COMPAT" in text:
        print(f"[AeroNode trim] EAP-method compat already present in {nw}")
        return

    if '#include "esp_idf_version.h"' not in text:
        text = re.sub(r'(#include\s+"esp_event\.h"\s*\n)', r'\1#include "esp_idf_version.h"\n', text, count=1)
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


def patch_network_wlan_make_ca_cert_optional(mp_root: Path) -> None:
    """Make ca_cert optional for PEAP/TTLS in PR #17234.

    Mirrors Android/iOS style "CA certificate: do not validate" by:
      1. removing ValueError("missing config param ca_cert");
      2. calling esp_eap_client_set_ca_cert() only when ca_cert is provided.
    """
    nw = mp_root / "ports" / "esp32" / "network_wlan.c"
    if not nw.exists():
        raise FileNotFoundError(f"Cannot find {nw}")

    text = nw.read_text(encoding="utf-8")
    original = text

    # Remove the hard requirement: if ca_cert is None -> raise ValueError.
    text = re.sub(
        r'\n[ \t]*if\s*\(\s*args\[ARG_ca_cert\]\.u_obj\s*==\s*mp_const_none\s*\)\s*\{\s*\n'
        r'[ \t]*mp_raise_ValueError\(MP_ERROR_TEXT\("missing config param ca_cert"\)\);\s*\n'
        r'[ \t]*\}\s*\n',
        '\n        // AeroNode: ca_cert is optional; skipping CA validation if None.\n',
        text,
        flags=re.M,
    )

    # Wrap nearby ca_cert extraction + esp_eap_client_set_ca_cert() call.
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if 'esp_eap_client_set_ca_cert' in line and 'AeroNode: ca_cert optional wrapper' not in ''.join(lines[max(0, i-5):i+1]):
            start = i
            for j in range(i - 1, max(-1, i - 10), -1):
                l = lines[j]
                if 'ARG_ca_cert' in l or 'ca_cert_len' in l or re.search(r'\bca_cert\b\s*=', l):
                    start = j
                if j < start and ('if (' in l or 'switch ' in l or re.match(r'\s*case\b', l)):
                    break

            while len(out) < start:
                out.append(lines[len(out)])

            indent = re.match(r'^(\s*)', lines[start]).group(1)
            out.append(indent + '// AeroNode: ca_cert optional wrapper; None means no CA validation.')
            out.append(indent + 'if (args[ARG_ca_cert].u_obj != mp_const_none) {')
            for k in range(start, i + 1):
                out.append(indent + '    ' + lines[k][len(indent):])
            out.append(indent + '}')
            i += 1
            continue

        if len(out) == i:
            out.append(line)
        i += 1

    text = '\n'.join(out) + ('\n' if original.endswith('\n') else '')

    if text == original:
        print(f"[AeroNode trim] PEAP no-CA patch made no changes; check PR code manually: {nw}")
    else:
        nw.write_text(text, encoding="utf-8")
        print(f"[AeroNode trim] patched {nw}")
        print("[AeroNode trim] PEAP/TTLS ca_cert is now optional; None = do not validate CA")


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
    patch_network_wlan_make_ca_cert_optional(mp_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
