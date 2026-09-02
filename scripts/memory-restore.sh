#!/usr/bin/env bash
# memory-restore.sh — 记忆库还原脚本 v2（hermes-memory-zh）
#
# 设计（v2，替代 v1 的"时间戳快照池"）：
#   - 真源为 snapshots/ 下两个固定文件：
#       memory.sql                 # 主还原源（SQL 文本，可审计）
#       memory_store.snapshot.db   # 兜底（一致性快照，直接 cp）
#   - "云端哪个最新"不靠文件名时间戳（那是 v1 事故的根源），固定文件无歧义：
#     最新 = git 里当前 HEAD 的那个。
#   - 判断"是否需要还原"：比对 facts 逻辑内容指纹 = COUNT + MAX(updated_at)
#     + 逻辑字段 md5。mtime 不可靠（Hermes 打开库会刷新 0 字节 .wal 的 mtime，
#     制造"本地刚写入"假象；主库 .db mtime 只在 checkpoint 时变）。
#     内容一致→无需还原；内容不同→MAX(updated_at) 大的为新方
#     （本地新则先 push，云端新则还原）。
#
# 模式：
#   memory-restore.sh check   # 检查报告（只报告，不覆盖）
#   memory-restore.sh apply   # 确认后强制还原（sql 优先，失败快照兜底；高危）
#   memory-restore.sh apply --yes   # 跳过交互确认（供 hook/脚本无人值守调用）
#
# 铁律（实测）：Hermes 运行中做文件级覆盖会数据混合/损坏库（database disk
# image is malformed）。SQL 还原走 SQLite 事务锁、运行中安全；快照 cp 兜底
# 必须在 Hermes 未运行时执行。覆盖后建议重启 Hermes 进程以读到干净数据。
set -euo pipefail

REPO="${HERMES_SYNC_REPO:-$HOME/hermes-sync}"
DB="${HERMES_MEMORY_DB:-$HOME/.hermes/memory_store.db}"
SNAPDIR="$REPO/snapshots"
SQL="$SNAPDIR/memory.sql"
SNAP="$SNAPDIR/memory_store.snapshot.db"
PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/memory-sync.py"

# ============================================================
# 新旧判据：不用文件 mtime，也不用 git commit_ts。
#   文件 mtime 不可靠 — Hermes 打开库会刷新 0 字节 .wal 的 mtime（制造
#   "本地刚写入"假象）；主库 .db mtime 又只在 checkpoint 时变。
#   可靠判据 = 比对 facts 的逻辑内容指纹：COUNT + MAX(updated_at) + 逻辑字段 md5。
#   （md5 只对逻辑字段算，不含 hrr_vector/embedding 等物理布局 — sqlite backup()
#   会重写物理页，文件级 md5 即使内容相同也不同，逻辑字段 md5 才是内容一致的证据。）
# ============================================================
# 输出三行：COUNT / MAX(updated_at) / 逻辑字段 md5；库不可读时输出 0 / '' / ERR
db_stats() {
  python3 -c '
import sqlite3, hashlib, sys
path = sys.argv[1]
try:
    c = sqlite3.connect(path)
    n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    m = c.execute("SELECT MAX(updated_at) FROM facts").fetchone()[0]
    m = m if m else ""
    rows = c.execute("SELECT fact_id, content, category, tags, trust_score, created_at, updated_at FROM facts ORDER BY fact_id").fetchall()
    rows = [tuple(("" if v is None else v) for v in r) for r in rows]
    h = hashlib.md5()
    for r in rows:
        h.update(repr(r).encode("utf-8"))
    c.close()
    print(n); print(m); print(h.hexdigest())
except Exception:
    print(0); print(""); print("ERR")
' "$1"
}

# 校验还原结果（facts 数 > 0 即视为成功）
restored_ok() {
  python3 -c "
import sqlite3, sys
try:
    c = sqlite3.connect('$DB')
    n = c.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    c.close()
    sys.exit(0 if n > 0 else 1)
except Exception:
    sys.exit(1)
"
}

hermes_running() { pgrep -f "hermes" >/dev/null 2>&1; }

evaluate() {
  RESTORE_NEEDED=0
  # 云端无真源
  if [ ! -f "$SNAP" ] && [ ! -f "$SQL" ]; then
    RESTORE_REASON="云端无记忆真源（snapshots/ 无 memory.sql / 固定快照）— 无法还原"
    return
  fi
  # 本地库不存在 → 直接还原
  if [ ! -f "$DB" ]; then
    RESTORE_NEEDED=1
    RESTORE_REASON="本地库不存在 — 直接还原为云端真源"
    return
  fi

  local l_stats c_stats l_cnt l_max l_fp c_cnt c_max c_fp
  l_stats="$(db_stats "$DB")"
  l_cnt="$(echo "$l_stats" | sed -n 1p)"
  l_max="$(echo "$l_stats" | sed -n 2p)"
  l_fp="$(echo "$l_stats" | sed -n 3p)"
  c_stats="$(db_stats "$SNAP")"
  c_cnt="$(echo "$c_stats" | sed -n 1p)"
  c_max="$(echo "$c_stats" | sed -n 2p)"
  c_fp="$(echo "$c_stats" | sed -n 3p)"

  echo "[检查] 本地 facts: count=$l_cnt  max_updated_at=$l_max"
  echo "[检查] 云端 facts: count=$c_cnt  max_updated_at=$c_max"

  # 逻辑内容完全一致 → 无需还原（覆盖是空操作且运行中覆盖会数据混合）
  if [ "$l_fp" != "ERR" ] && [ "$c_fp" != "ERR" ] && [ "$l_fp" = "$c_fp" ]; then
    RESTORE_NEEDED=0
    RESTORE_REASON="本地与云端记忆内容一致（facts=$l_cnt 条，逻辑指纹相同）— 无需还原"
    return
  fi

  # 内容不同 → 用真实数据更新时间 MAX(updated_at) 判谁新（ISO 串可字典序比较）
  if [ -n "$l_max" ] && [ -n "$c_max" ] && [ "$l_max" \> "$c_max" ]; then
    RESTORE_NEEDED=0
    RESTORE_REASON="本地记忆比云端新（本地最新 $l_max > 云端 $c_max）— 可能含未 push 的新记忆，先跑 sync push"
    return
  fi

  RESTORE_NEEDED=1
  RESTORE_REASON="云端记忆比本地新（云端最新 $c_max > 本地 $l_max，或本地库不可读）— 建议还原"
}

do_restore() {
  # 覆盖前备份本地库
  local bak
  if [ -f "$DB" ]; then
    bak="$DB.bak.$(date +%Y%m%dT%H%M%S)"
    cp "$DB" "$bak"
    echo "[还原] 已备份本地库 -> $bak"
  fi

  # 主还原：sql 文本（可审计，含完整 schema+数据；走 SQLite 锁，运行中安全）
  local ok=0
  if [ -f "$SQL" ]; then
    echo "[还原] 优先用 memory.sql 还原（sql + FTS rebuild）..."
    if python3 "$PY" restore && restored_ok; then
      ok=1
      echo "[还原] ✓ sql 还原成功"
    else
      echo "[还原] ✗ sql 还原失败，转快照兜底"
    fi
  else
    echo "[还原] 无 memory.sql，直接用固定快照"
  fi

  # 兜底：快照直接 cp（本身完整一致，免 rebuild）
  # 只在 Hermes 未运行时执行——文件级覆盖会绕过 SQLite 锁，运行中写入会损坏库
  if [ "$ok" = "0" ] && [ -f "$SNAP" ]; then
    if hermes_running; then
      echo "[还原] ✗ 快照兜底已跳过（Hermes 运行中，cp 覆盖会损坏库）"
      echo "    sql 还原失败，请退出 Hermes 后重新 apply"
    else
      echo "[还原] 快照兜底: cp $SNAP -> $DB"
      cp "$SNAP" "$DB.tmp"
      rm -f "$DB-wal" "$DB-shm"          # 清 WAL/SHM，避免旧页残留
      mv "$DB.tmp" "$DB"
      restored_ok && ok=1 && echo "[还原] ✓ 快照兜底成功"
    fi
  fi

  if [ "$ok" != "1" ]; then
    echo "[还原] ✗ 还原失败（无可用真源）。可从备份恢复: cp $bak $DB"
    exit 1
  fi
  # 清理 WAL/SHM：只在 Hermes 未运行时执行（运行中删除会损坏连接）
  if ! hermes_running; then
    rm -f "$DB-wal" "$DB-shm"
  fi
  if hermes_running; then
    echo "[还原] ✓ sql 还原完成（Hermes 运行中，已通过 SQLite 锁机制写入）"
    echo "    下次检索即可读到新数据；保险起见建议重启 Hermes"
  else
    echo "[还原] ⚠️ 重启 Hermes 进程后生效"
  fi
}

cmd="${1:-check}"
case "$cmd" in
  check)
    evaluate
    echo "----------------------------------------------"
    if [ "$RESTORE_NEEDED" = "1" ]; then
      echo "判断: 需要还原"
      echo "理由: $RESTORE_REASON"
      echo "执行: bash $0 apply"
      echo "      （高危，确认后执行；会覆盖本地 memory_store.db，先备份 .bak）"
    else
      echo "判断: 无需还原"
      echo "理由: $RESTORE_REASON"
    fi
    exit 0
    ;;
  apply)
    # 高危确认（--yes 跳过交互，供 hook/无人值守）
    yes=0
    [ "${2:-}" = "--yes" ] && yes=1
    if [ "$yes" = "0" ]; then
      if hermes_running; then
        echo "⚠️ 检测到 Hermes 正在运行！将走 SQL 还原（安全），快照兜底自动跳过。"
        echo "   继续请按 y:"
        read -r ans; [ "$ans" != "y" ] && { echo "已取消"; exit 1; }
      fi
      echo "将执行还原（覆盖前备份 .bak）。确认请按 y:"
      read -r ans; [ "$ans" != "y" ] && { echo "已取消"; exit 1; }
    fi
    # --yes 模式：Hermes 运行中允许 SQL 还原，快照 cp 兜底自动跳过
    evaluate
    if [ "$RESTORE_NEEDED" != "1" ]; then
      echo "无需还原: $RESTORE_REASON"
      exit 0
    fi
    echo "----------------------------------------------"
    echo "将执行还原: $RESTORE_REASON"
    do_restore
    ;;
  *)
    echo "usage: $0 {check|apply [--yes]}"; exit 1;;
esac
