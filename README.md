# AeroNode MicroPython Enterprise Lite for ESP32-C3 SuperMini

目标：给 ESP32-C3FH4 / 4MB Flash / 无 PSRAM 的 C3 SuperMini 构建一个能连 WPA2-Enterprise 校园网的 MicroPython 固件，同时尽量保留气象站需要的功能。

## 你会得到什么

构建成功后生成：

```text
output/firmware.bin
```

刷入方式：

```bat
flash_firmware.bat COM73
```

## v3 修复说明

v2 的 GitHub Actions 在执行 `make submodules` 时没有传入 `BOARD=ESP32_GENERIC_C3`，MicroPython Makefile 会回落到默认 `ESP32_GENERIC`，于是 CMake 去找 `xtensa-esp32-elf-gcc`。但 C3 是 RISC-V，脚本只安装了 `esp32c3` 工具链，所以会报 `xtensa-esp32-elf-gcc is not a full path and was not found in the PATH`。

v3 已修复为：

```bash
make BOARD=ESP32_GENERIC_C3 submodules
make BOARD=ESP32_GENERIC_C3 -j2
```

本地 WSL 脚本也做了同样修复。

## 默认路线

默认构建 MicroPython PR #17234，因为它比 #17789 更完整，支持 EAP-PWD、PEAP、TTLS，并且 PR 讨论中维护者也建议优先参考 #17234。#17789 可作为备用。

## 本地一键构建，Windows + WSL

1. 第一次需要安装 WSL Ubuntu。管理员 PowerShell：

```powershell
wsl --install -d Ubuntu
```

2. 重启电脑，打开一次 Ubuntu，设置用户名密码。
3. 回到本目录，双击：

```text
local_wsl_build.bat
```

第一次会下载 ESP-IDF、MicroPython、工具链，比较大。以后会复用 `work/`。

## GitHub Actions 云构建，避免本地编译地狱

1. 新建一个私有 GitHub 仓库。
2. 把本包内容上传进去。
3. 把 `github-actions/.github/workflows/build.yml` 复制/保留到仓库的 `.github/workflows/build.yml`。
4. GitHub 页面：Actions -> Build AeroNode MicroPython Enterprise Lite -> Run workflow。
5. 完成后下载 Artifact，里面有 `firmware.bin`。

不要把校园网账号和密码写进仓库。

## 裁剪策略

保留：

- WiFi / network / socket
- BLE / bluetooth
- VFS / LittleFS / 文件系统
- machine / I2C / ADC / Timer / UART / SPI
- PEAP/MSCHAPv2 所需 TLS/mbedTLS

默认裁剪：

- btree
- WebREPL frozen entry
- Python `_thread` 模块，C3 单核且 AeroNode 当前架构不需要 Python 线程

如果你以后需要 `_thread`，本地构建前在 WSL 中运行：

```bash
KEEP_THREAD=1 bash scripts/build_wsl.sh
```

## 切到 #17789 备用 PR

本地 WSL：

```bash
MPY_PR=17789 bash scripts/build_wsl.sh
```

GitHub Actions：运行 workflow 时把 `pr` 改为 `17789`。

## 连接校园网示例

见：

```text
examples/enterprise_connect_peap.py
```

常见学校无证书账号密码 WiFi 大概率是 PEAP + MSCHAPv2。若学校强制 CA 校验，则仍需要上传学校/eduroam CA 证书并传入 `ca_cert`。


## v2 修正说明

上一版默认 ESP-IDF 写成了 `v5.4.0`。Espressif 的实际 tag 通常是 `v5.4`、`v5.4.1`、`v5.4.2` 这种形式，`v5.4.0` / `v5.3.0` 会在 `git clone -b` 阶段直接 exit 128。

本版默认改为 `v5.4.2`，并在克隆前用 `git ls-remote --tags` 检查 tag 是否存在。若仍失败，优先尝试：

```bash
IDF_VERSION=v5.5.2 MPY_PR=17234 bash scripts/build_wsl.sh
```

GitHub Actions 手动运行时，`idf_version` 填 `v5.4.2` 或 `v5.5.2`，不要填 `v5.4.0` / `v5.3.0`。
