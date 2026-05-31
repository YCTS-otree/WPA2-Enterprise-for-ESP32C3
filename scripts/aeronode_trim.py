#!/usr/bin/env python3
# AeroNode MicroPython ESP32-C3 trim helper
# Fix v8: strict PEAP no-CA patch, IDF 5.4 EAP shim, EAP min_sec fix.

from __future__ import annotations
import re
import sys
from pathlib import Path


def replace_define(text: str, name: str, value: str, append: bool = True) -> str:
    pat = re.compile(rf"^\s*#\s*define\s+{re.escape(name)}\b.*$", re.M)
    line = f"#define {name} {value}"
    if pat.search(text):
        return pat.sub(line, text, count=1)
    return text.rstrip() + "\n\n// AeroNode lite overrides\n" + line + "\n" if append else text


def replace_sdkconfig(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"^\s*{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pat.search(text):
        return pat.sub(line, text, count=1)
    return text.rstrip() + "\n" + line + "\n"


def insert_after_include(text: str, include_line: str, block: str, marker: str) -> str:
    if marker in text:
        return text
    if include_line in text:
        return text.replace(include_line, include_line + block, 1)
    matches = list(re.finditer(r'^#include\s+[<"].*[>"]\s*$', text, flags=re.M))
    if matches:
        pos = matches[-1].end()
        return text[:pos] + block + text[pos:]
    return block + text


def patch_mpconfigport(mp_root: Path) -> None:
    cfg = mp_root / "ports" / "esp32" / "mpconfigport.h"
    text = cfg.read_text(encoding="utf-8")

    text = replace_define(text, "MICROPY_PY_THREAD", "(0)")
    text = replace_define(text, "MICROPY_PY_THREAD_GIL", "(0)")
    text = replace_define(text, "MICROPY_PY_BLUETOOTH", "(0)")

    for name in (
        "MICROPY_BLUETOOTH_NIMBLE",
        "MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE",
        "MICROPY_PY_BLUETOOTH_ENABLE_L2CAP_CHANNELS",
        "MICROPY_PY_WEBREPL",
        "MICROPY_PY_WEBSOCKET",
        "MICROPY_PY_SOCKET_EVENTS",
        "MICROPY_PY_ESPNOW",
    ):
        text = replace_define(text, name, "(0)", append=False)

    cfg.write_text(text, encoding="utf-8")
    print("[AeroNode trim] mpconfigport patched")


def patch_sdkconfig(mp_root: Path, board: str = "ESP32_GENERIC_C3") -> None:
    sdk = mp_root / "ports" / "esp32" / "boards" / board / "sdkconfig.board"
    text = sdk.read_text(encoding="utf-8") if sdk.exists() else ""

    for key in ("CONFIG_BT_ENABLED", "CONFIG_BT_NIMBLE_ENABLED", "CONFIG_BT_BLUEDROID_ENABLED"):
        text = replace_sdkconfig(text, key, "n")

    for key in ("CONFIG_ESP_WIFI_STA_WPA2_ENT", "CONFIG_WPA_MBEDTLS_CRYPTO", "CONFIG_WPA_MBEDTLS_TLS_CLIENT"):
        text = replace_sdkconfig(text, key, "y")

    text = replace_sdkconfig(text, "CONFIG_ESP_WIFI_SOFTAP_SUPPORT", "n")

    sdk.write_text(text.rstrip() + "\n", encoding="utf-8")
    print("[AeroNode trim] sdkconfig patched")


def patch_network_wlan(mp_root: Path) -> None:
    nw = mp_root / "ports" / "esp32" / "network_wlan.c"
    text = nw.read_text(encoding="utf-8")

    if '#include "esp_idf_version.h"' not in text:
        text = re.sub(
            r'(#include\s+"esp_event\.h"\s*\n)',
            r'\1#include "esp_idf_version.h"\n',
            text,
            count=1,
        )
        if '#include "esp_idf_version.h"' not in text:
            text = '#include "esp_idf_version.h"\n' + text

    idf54_shim = '''
// AeroNode: ESP-IDF v5.4.x compatibility for PR #17234.
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
    text = insert_after_include(
        text,
        '#include "esp_eap_client.h"',
        idf54_shim,
        "AERONODE_IDF54_EAP_METHODS_COMPAT",
    )

    no_ca_shim = '''
// AeroNode: empty CA cert means no CA validation.
#ifndef AERONODE_NO_CA_CERT_COMPAT
#define AERONODE_NO_CA_CERT_COMPAT (1)
#define esp_eap_client_set_ca_cert(ca_cert, ca_cert_len) (((ca_cert_len) == 0) ? ESP_OK : esp_eap_client_set_ca_cert((ca_cert), (ca_cert_len)))
#endif
'''
    text = insert_after_include(
        text,
        '#include "esp_eap_client.h"',
        no_ca_shim,
        "AERONODE_NO_CA_CERT_COMPAT",
    )

    before_hard_error_count = text.count("missing config param ca_cert")

    # PR #17234 uses "missing config param ca_cert." with a period on some versions.
    text, removed_checks = re.subn(
        r'\n[ \t]*if\s*\(\s*args\[ARG_ca_cert\]\.u_obj\s*==\s*mp_const_none\s*\)\s*\{\s*\n'
        r'[ \t]*mp_raise_ValueError\(MP_ERROR_TEXT\("missing config param ca_cert\.?"\)\);\s*\n'
        r'[ \t]*\}\s*',
        '\n        // AeroNode: ca_cert=None allowed; no CA validation.\n',
        text,
        flags=re.M,
    )

    old_get = 'mp_obj_str_get_data(args[ARG_ca_cert].u_obj, &ca_cert_len)'
    new_get = '((args[ARG_ca_cert].u_obj == mp_const_none) ? (ca_cert_len = 0, "") : mp_obj_str_get_data(args[ARG_ca_cert].u_obj, &ca_cert_len))'
    patched_get_data = text.count(old_get)
    text = text.replace(old_get, new_get)

    parse_line = "mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);"
    if "AeroNode: EAP implies WPA2 Enterprise" not in text:
        if parse_line not in text:
            raise RuntimeError("Cannot find mp_arg_parse_all line; PR code shape changed")
        text = text.replace(
            parse_line,
            parse_line + '''
    // AeroNode: EAP implies WPA2 Enterprise.
    if (args[ARG_eap_method].u_int != WIFI_AUTH_EAP_NONE
        && args[ARG_min_sec].u_int == WIFI_AUTH_WPA2_PSK) {
        args[ARG_min_sec].u_int = WIFI_AUTH_WPA2_ENTERPRISE;
    }''',
            1,
        )

    nw.write_text(text, encoding="utf-8")
    print(
        "[AeroNode trim] network_wlan patched: "
        f"old_ca_errors={before_hard_error_count}, "
        f"removed_checks={removed_checks}, "
        f"patched_get_data={patched_get_data}"
    )

    if "missing config param ca_cert" in text:
        raise RuntimeError("no-CA patch failed: ca_cert hard error is still present")
    if removed_checks < 1:
        raise RuntimeError("no-CA patch failed: removed_checks=0")


def main() -> int:
    mp_root = Path(sys.argv[1]).resolve() if len(sys.argv) >= 2 else (Path.cwd() / "work" / "micropython").resolve()
    if not (mp_root / "ports" / "esp32").exists():
        raise RuntimeError(f"not a MicroPython tree: {mp_root}")

    patch_mpconfigport(mp_root)
    patch_sdkconfig(mp_root)
    patch_network_wlan(mp_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
