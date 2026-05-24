# ESP32-C3 MicroPython WPA2-Enterprise / PEAP-MSCHAPv2 example
# 适合“学校 WiFi：手机只填账号+密码、没有证书”的常见场景。
# 注意：不要把真实账号密码提交到 GitHub。

import network
import time
import gc

SSID = "你的校园网SSID"
IDENTITY = "anonymous"      # 不确定时可先填用户名；部分学校可填 anonymous@学校域名
USERNAME = "你的账号"
PASSWORD = "你的密码"

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
gc.collect()

# PR #17234 API：推荐路线
if hasattr(wlan, "eap_connect"):
    # 无证书校园网：先试 disable_time_check=True；若学校强制 CA 校验，需上传 CA 证书后再传 ca_cert。
    wlan.eap_connect(
        ssid=SSID,
        eap_method=wlan.EAP_PEAP,
        username=USERNAME,
        password=PASSWORD,
        identity=IDENTITY,
        disable_time_check=True,
    )

# PR #17789 API：备用路线
elif hasattr(wlan, "wpa2_ent_enable"):
    wlan.wpa2_ent_enable()
    wlan.wpa2_ent_set_identity(IDENTITY)
    wlan.wpa2_ent_set_username(USERNAME)
    wlan.wpa2_ent_set_password(PASSWORD)
    wlan.connect(SSID)

else:
    raise RuntimeError("当前固件没有 WPA2-Enterprise API；请确认刷入的是 Enterprise Lite 固件")

for i in range(30):
    if wlan.isconnected():
        print("Connected:", wlan.ifconfig())
        break
    print("connecting...", i, "status=", wlan.status(), "free=", gc.mem_free())
    time.sleep(1)
else:
    print("FAILED status=", wlan.status())
    print("常见原因：账号格式错误、学校禁用证书绕过、AP 不支持该 EAP 参数、密码错误。")
