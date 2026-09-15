#!/bin/sh
# 确保 /tmp/vcheck/ocr_tool 存在(Swift+Vision OCR;macOS 限定)。
# 源码以仓库内 scripts/audit/vcheck/ocr.swift 为准(/tmp 会被系统清理,二进制丢了跑本脚本重建)。
# 用法: ensure_ocr_tool.sh [--force]   成功时打印二进制路径。
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)/ocr.swift"
DEST="${OCR_TOOL:-/tmp/vcheck/ocr_tool}"

if [ -x "$DEST" ] && [ "${1:-}" != "--force" ]; then
    echo "$DEST"
    exit 0
fi
mkdir -p "$(dirname "$DEST")"
swiftc -O -o "$DEST" "$SRC"
echo "$DEST"
