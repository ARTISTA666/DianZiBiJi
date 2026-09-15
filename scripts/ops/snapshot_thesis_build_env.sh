#!/bin/sh
# 论文构建环境快照:把 /tmp/crlt/projects/thesis-ahnu-master 整体打包到 agent-work/freeze/。
# 背景:/tmp 会被系统清理,构建工程已三次"失血";环境健康时定期跑本脚本,失血后用
# restore_thesis_build_env.sh 一条命令还原,不再靠台账考古。快照存 agent-work/(不入库)。
# 用法: snapshot_thesis_build_env.sh [输出目录]   默认 <repo>/agent-work/freeze,保留最近 3 份。
set -eu
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_PARENT="/tmp/crlt/projects"
SRC="$SRC_PARENT/thesis-ahnu-master"
OUT_DIR="${1:-$REPO/agent-work/freeze}"

if [ ! -d "$SRC" ]; then
    echo "构建工程不存在: $SRC(可能已被清理,只能走 restore 路径)" >&2
    exit 1
fi
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$OUT_DIR/thesis-build-env-$STAMP.tar.gz"

tar -C "$SRC_PARENT" -czf "$OUT" thesis-ahnu-master
shasum -a 256 "$OUT" > "$OUT.sha256"
echo "快照完成: $OUT ($(du -h "$OUT" | cut -f1))"

# 只保留最近 3 份快照
ls -t "$OUT_DIR"/thesis-build-env-*.tar.gz 2>/dev/null | tail -n +4 | while IFS= read -r old; do
    rm -f "$old" "$old.sha256"
    echo "清理旧快照: $old"
done
