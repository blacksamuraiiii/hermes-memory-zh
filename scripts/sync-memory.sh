#!/usr/bin/env bash
# sync-memory.sh — 一致性快照同步脚本（hermes-memory-zh 记忆库）
#
# 在两台机器间用 git 同步 SQLite 记忆库的"一致性快照"，避免直接同步热库
# （WAL 不一致 / 二进制膨胀 / 并发锁）的问题。
#
# 模型：云端 snapshots/ = 快照池（唯一真源）。快照文件名带 UTC 时间戳，比较
# 文件名即可判断新旧（不依赖跨机 mtime）。
#
#   sync-memory.sh push    # 退出 Hermes 后调用：生成快照→上传→清理超期
#   sync-memory.sh pull    # 启动 Hermes 前调用：拉云端最新快照→覆盖本地
#
# 建议在两机切换时：用完的机器 push，要用的机器 pull。
#
# 保留策略：默认只保留 90 天（3 个月）内的快照文件。注意 git 历史里的旧 blob
# 不因删除文件而消失（接受增长，偶尔 git gc --aggressive）。
set -euo pipefail

REPO="${HERMES_SYNC_REPO:-$HOME/hermes-sync}"
DB="${HERMES_MEMORY_DB:-$HOME/.hermes/memory_store.db}"
SNAP_DIR="$REPO/snapshots"
RETENTION_DAYS="${HERMES_SNAP_RETENTION:-90}"

mkdir -p "$SNAP_DIR"

latest_snap() { ls -1 "$SNAP_DIR"/snap-*.db 2>/dev/null | sort | tail -1 || true; }

cmd="${1:-pull}"

case "$cmd" in
  push)
    if [ ! -f "$DB" ]; then echo "no DB at $DB"; exit 0; fi
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    snap="$SNAP_DIR/snap-$ts.db"
    # 一致性快照（含 WAL 未 checkpoint 的数据）。用 python 标准库 sqlite3，
    # 不依赖 sqlite3 CLI。
    python3 - "$DB" "$snap" << 'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
print("backup ok:", len(open(sys.argv[2],'rb').read()), "bytes")
PY
    echo "snapshot: $(basename "$snap")"
    # 清理超期快照文件
    find "$SNAP_DIR" -name 'snap-*.db' -mtime +"$RETENTION_DAYS" -delete
    ( cd "$REPO" && git add snapshots/ && \
      git commit -q -m "memory snapshot $ts" || true && \
      git pull --rebase --autostash -q || true && \
      git push -q || echo "push failed (retry later)" )
    ;;
  pull)
    newest="$(latest_snap)"
    if [ -z "$newest" ]; then echo "no snapshot in $SNAP_DIR (run push first)"; exit 0; fi
    prev="$(cat "$REPO/.last-sync-snapshot" 2>/dev/null || true)"
    if [ -n "$prev" ] && [ "$(basename "$newest")" = "$prev" ]; then
      echo "already at latest: $prev"; exit 0
    fi
    # 防呆：Hermes 进程在跑时覆盖会损坏活动库
    if pgrep -f "hermes" >/dev/null 2>&1; then
      echo "WARN: hermes running — aborting restore"; exit 1
    fi
    cp "$newest" "$DB.tmp"
    rm -f "$DB-wal" "$DB-shm"
    mv "$DB.tmp" "$DB"
    echo "$(basename "$newest")" > "$REPO/.last-sync-snapshot"
    echo "restored $(basename "$newest") -> $DB"
    ;;
  *)
    echo "usage: $0 {push|pull}"; exit 1;;
esac
