#!/usr/bin/env python3
"""memory-sync.py — 记忆库同步引擎（hermes-memory-zh，纯 python 标准库 sqlite3）

v2 设计：云端 snapshots/ 只维护两个固定文件作为唯一真源：
  - memory.sql                    # SQL 文本 dump（主还原源，可 diff 审计）
  - memory_store.snapshot.db      # 一致性快照（兜底，sql 还原失败时直接 cp）

子命令：
  push     生成 memory.sql + 固定快照（覆盖写，供 sync.sh push 调用）
  restore  用 memory.sql 还原本地库（sql 优先；失败由调用方快照兜底）
  backup   仅更新固定快照
  dump     仅更新 memory.sql
  verify   校验本地库完整性（facts 数 + FTS 检索），供还原后验证

路径均可通过环境变量覆盖：
  HERMES_MEMORY_DB  本地记忆库路径（默认 ~/.hermes/memory_store.db）
  HERMES_SYNC_REPO  真源仓库路径（默认 ~/hermes-sync）
"""
import sqlite3, os, sys

DB      = os.path.expanduser(os.environ.get("HERMES_MEMORY_DB", "~/.hermes/memory_store.db"))
REPO    = os.path.expanduser(os.environ.get("HERMES_SYNC_REPO", "~/hermes-sync"))
SNAPDIR = os.path.join(REPO, "snapshots")
SQL     = os.path.join(SNAPDIR, "memory.sql")
SNAP    = os.path.join(SNAPDIR, "memory_store.snapshot.db")
FTS     = ('facts_fts', 'facts_fts_tokenized')

# 跳过 FTS shadow 表（派生索引，不 dump，恢复后 rebuild）
def _skip(name):
    return name.startswith('facts_fts') and name not in FTS

def dump_memory(src_db, out_sql):
    """SQL 文本 dump：普通表 + 虚拟表 CREATE，跳过 FTS shadow / sqlite_sequence。"""
    os.makedirs(os.path.dirname(out_sql), exist_ok=True)
    src = sqlite3.connect(src_db)
    cur = src.cursor()
    real, vt = [], []
    for typ, name, sql in cur.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','virtual') ORDER BY rootpage"):
        if _skip(name):
            continue
        if sql and sql.strip().upper().startswith('CREATE VIRTUAL TABLE'):
            vt.append(sql)
        elif typ == 'table' and sql and name != 'sqlite_sequence':
            real.append(sql)
    lines = ["BEGIN;"]
    # 普通表先建（facts 最前，虚拟表 content= 引用它），再虚拟表，再数据
    for s in sorted(real, key=lambda s: 0 if 'CREATE TABLE "facts"' in s else 1):
        lines.append(s + ";")
    for s in vt:
        lines.append(s + ";")
    for name in ('facts', 'entities', 'fact_entities', 'memory_banks'):
        try:
            rows = cur.execute(f'SELECT * FROM "{name}"').fetchall()
            cols = [d[1] for d in cur.execute(f'PRAGMA table_info("{name}")').fetchall()]
        except Exception:
            continue
        for r in rows:
            vals = []
            for v in r:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bytes):
                    vals.append("X'" + v.hex() + "'")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            lines.append(f'INSERT INTO "{name}"({",".join(cols)}) VALUES({",".join(vals)});')
    lines.append("COMMIT;")
    with open(out_sql, 'w') as f:
        f.write("\n".join(lines))
    src.close()

def backup_snapshot(src_db, out_snap):
    """固定快照：sqlite backup() 一致性拷贝（含 WAL 未 checkpoint 数据）。"""
    os.makedirs(os.path.dirname(out_snap), exist_ok=True)
    src = sqlite3.connect(src_db)
    dst = sqlite3.connect(out_snap)
    src.backup(dst)
    dst.close()
    src.close()

def restore_sql(sql_path, dst_db):
    """sql 还原：先清空目标库现有表（避免 table already exists），
    executescript + rebuild FTS 索引。纯 SQL 操作，Hermes 运行中安全。"""
    dst = sqlite3.connect(dst_db, timeout=10)
    dst.execute("PRAGMA busy_timeout=5000")
    # 枚举现有所有表/视图/触发器，DROP 清空后再灌入云端 schema+数据。
    # 跳过 FTS shadow 表（*_data/_idx/_docsize/_config 等）——虚拟表 DROP 会连带清理。
    names = dst.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','view','trigger')"
    ).fetchall()
    for name, typ in names:
        if typ == 'table' and any(
            name.endswith(s) for s in ('_data', '_idx', '_docsize', '_config', '_content', '_segments', '_segdir', '_stat')
        ):
            continue
        dst.execute(f'DROP {typ.upper()} IF EXISTS "{name}"')
    dst.executescript(open(sql_path).read())
    for t in FTS:
        dst.execute(f"INSERT INTO {t}({t}) VALUES('rebuild')")
    dst.commit()
    dst.close()

def verify(db_path):
    """完整性校验：facts 数 + FTS 索引数。返回 (facts_n, fts_n)。"""
    c = sqlite3.connect(db_path)
    n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    f = c.execute(f"SELECT COUNT(*) FROM {FTS[0]}").fetchone()[0]
    c.close()
    return n, f

def source_healthy(db_path):
    """push 前保护：源库 PRAGMA integrity_check 必须 ok，且 facts 表可读非空。
    若库已损坏（btree 错乱 / malformed），dump 出的 memory.sql 会是空的、
    backup 出的快照也带病 —— 一旦提交就污染云端真源。因此 push 前强制校验，
    损坏则拒绝生成。"""
    try:
        c = sqlite3.connect(db_path)
        r = c.execute("PRAGMA integrity_check").fetchone()
        n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        c.close()
        return r is not None and r[0] == "ok" and n > 0
    except Exception:
        return False

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'push'
    if cmd in ('push', 'backup', 'dump'):
        if not source_healthy(DB):
            sys.exit("✗ 源库损坏或不可读（integrity_check 非 ok / facts 为空）"
                     "\n  拒绝生成真源，防止污染云端。"
                     "\n  修复: 退出 Hermes 后跑 memory-restore.sh apply --yes 从云端还原")
    if cmd == 'push':
        dump_memory(DB, SQL)
        backup_snapshot(DB, SNAP)
        print(f"memory.sql={os.path.getsize(SQL)}B snapshot={os.path.getsize(SNAP)}B")
    elif cmd == 'restore':
        restore_sql(SQL, DB)
        print("restored via sql:", verify(DB))
    elif cmd == 'backup':
        backup_snapshot(DB, SNAP)
        print("snapshot updated:", os.path.getsize(SNAP))
    elif cmd == 'dump':
        dump_memory(DB, SQL)
        print("memory.sql updated:", os.path.getsize(SQL))
    elif cmd == 'verify':
        print("verify:", verify(DB))
    else:
        sys.exit(f"usage: {sys.argv[0]} {{push|restore|backup|dump|verify}}")

if __name__ == '__main__':
    main()
