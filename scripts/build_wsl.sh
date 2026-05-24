#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
WORK="$ROOT/work"
OUT="$ROOT/output"
LOG="$WORK/build.log"
IDF_VERSION="${IDF_VERSION:-v5.4.2}"
MPY_PR="${MPY_PR:-17234}"
BOARD="${BOARD:-ESP32_GENERIC_C3}"
JOBS="${JOBS:-$(nproc)}"

mkdir -p "$WORK" "$OUT"
exec > >(tee "$LOG") 2>&1

echo "[INFO] AeroNode MicroPython Enterprise Lite builder"
echo "[INFO] IDF_VERSION=$IDF_VERSION MPY_PR=$MPY_PR BOARD=$BOARD JOBS=$JOBS"

echo "[INFO] 安装 Linux 构建依赖。第一次会比较久。"
sudo apt-get update
sudo apt-get install -y \
  git wget curl flex bison gperf python3 python3-pip python3-venv \
  cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0 \
  make gcc g++ build-essential pkg-config

cd "$WORK"
if [ ! -d esp-idf/.git ]; then
  echo "[INFO] 克隆 ESP-IDF $IDF_VERSION"
  git ls-remote --exit-code --tags https://github.com/espressif/esp-idf.git "refs/tags/$IDF_VERSION"
  git clone --branch "$IDF_VERSION" --depth 1 --recursive https://github.com/espressif/esp-idf.git esp-idf
  git -C esp-idf submodule update --init --recursive --depth 1 --depth 1
else
  echo "[INFO] 复用已有 ESP-IDF，并切换到 $IDF_VERSION"
  git -C esp-idf fetch --tags
  git -C esp-idf checkout "$IDF_VERSION"
  git -C esp-idf submodule update --init --recursive --depth 1
fi

if [ ! -f esp-idf/export.sh ]; then
  echo "[ERROR] ESP-IDF 目录异常。删除 work/esp-idf 后重试。"
  exit 1
fi

echo "[INFO] 安装 ESP-IDF 工具链：esp32c3"
(cd esp-idf && ./install.sh esp32c3)
# shellcheck disable=SC1091
source "$WORK/esp-idf/export.sh"

if [ ! -d micropython/.git ]; then
  echo "[INFO] 克隆 MicroPython"
  git clone https://github.com/micropython/micropython.git micropython
fi
cd "$WORK/micropython"

echo "[INFO] 获取 MicroPython PR #$MPY_PR"
git fetch origin
if git fetch origin "pull/$MPY_PR/head:pr-$MPY_PR"; then
  git checkout "pr-$MPY_PR"
else
  echo "[ERROR] 无法获取 PR #$MPY_PR。默认推荐 #17234；备用可尝试：MPY_PR=17789 bash scripts/build_wsl.sh"
  exit 1
fi

echo "[INFO] 更新 MicroPython 子模块"
git submodule update --init lib/berkeley-db lib/micropython-lib lib/tinyusb lib/mbedtls 2>/dev/null || true

echo "[INFO] 应用 AeroNode Lite 裁剪：保留 WiFi/BLE/文件系统/PEAP 所需 TLS，裁掉 btree/WebREPL 等边缘项"
python3 "$ROOT/scripts/aeronode_trim.py" "$WORK/micropython"

echo "[INFO] 构建 mpy-cross"
make -C mpy-cross -j"$JOBS"

echo "[INFO] 构建 ESP32-C3 固件"
cd ports/esp32
make BOARD="$BOARD" submodules
make BOARD="$BOARD" -j"$JOBS"

FW="build-${BOARD}/firmware.bin"
if [ ! -f "$FW" ]; then
  echo "[ERROR] 未找到 $FW；请检查 build.log。"
  find . -name firmware.bin -print
  exit 1
fi
cp "$FW" "$OUT/firmware.bin"
cp "build-${BOARD}/micropython.bin" "$OUT/" 2>/dev/null || true
cp "build-${BOARD}/partition_table/partition-table.bin" "$OUT/partitions.bin" 2>/dev/null || true
cp "build-${BOARD}/bootloader/bootloader.bin" "$OUT/bootloader.bin" 2>/dev/null || true

echo "[OK] 输出完成：$OUT/firmware.bin"
ls -lh "$OUT/firmware.bin"
