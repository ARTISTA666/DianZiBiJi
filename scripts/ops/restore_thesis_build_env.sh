#!/bin/sh
# 论文构建环境恢复:把 snapshot_thesis_build_env.sh 的快照解回 /tmp/crlt/projects/,
# 并自动跑图片引用完整性 preflight(台账 T-047 教训:重建前必查引用,防二次失血)。
# 用法:
#   restore_thesis_build_env.sh --check-only                 # 只对现有工程跑 preflight
#   restore_thesis_build_env.sh SNAPSHOT.tar.gz [--force]    # 解包恢复 + preflight
# 工程已存在时需 --force(旧目录改名 thesis-ahnu-master.bak-<时间戳> 保留)。
set -eu
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PROJ_PARENT="/tmp/crlt/projects"
PROJ="$PROJ_PARENT/thesis-ahnu-master"
INTEGRITY="$REPO/scripts/audit/thesis_asset_integrity.py"

MODE="${1:-}"
if [ -z "$MODE" ]; then
    echo "用法: $0 --check-only | SNAPSHOT.tar.gz [--force]" >&2
    exit 2
fi

if [ "$MODE" = "--check-only" ]; then
    exec python3 "$INTEGRITY" --project "$PROJ"
fi

SNAP="$MODE"
FORCE=0
[ "${2:-}" = "--force" ] && FORCE=1

if [ ! -f "$SNAP" ]; then
    echo "快照不存在: $SNAP" >&2
    exit 2
fi
if [ -f "$SNAP.sha256" ]; then
    shasum -a 256 -c "$SNAP.sha256" >/dev/null
    echo "校验和 OK"
else
    echo "警告: 找不到 $SNAP.sha256,跳过校验" >&2
fi

if [ -d "$PROJ" ]; then
    if [ "$FORCE" -ne 1 ]; then
        echo "目标已存在: $PROJ(确认覆盖请加 --force,旧目录会改名保留)" >&2
        exit 1
    fi
    BAK="$PROJ.bak-$(date +%Y%m%d-%H%M)"
    mv "$PROJ" "$BAK"
    echo "旧工程已挪到: $BAK"
fi

mkdir -p "$PROJ_PARENT"
tar -C "$PROJ_PARENT" -xzf "$SNAP"
echo "解包完成: $PROJ"
python3 "$INTEGRITY" --project "$PROJ" || {
    echo "preflight 发现缺失引用,请先按上面清单补齐再编译" >&2
    exit 1
}
cat <<'EOF'
下一步(参考 reviews/round-04/视觉核验管线.md):
  python3 reviews/round-04/convert-enhanced.py        # md -> extraTex 章节重生成
  cd /tmp/crlt/projects/thesis-ahnu-master && latexmk -xelatex -g main.tex
  python3 scripts/audit/thesis_build_stats.py --build-dir /tmp/crlt/projects/thesis-ahnu-master
EOF
