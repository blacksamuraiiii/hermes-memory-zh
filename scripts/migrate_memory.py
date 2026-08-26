#!/usr/bin/env python3
"""Migrate Hermes built-in MEMORY.md / USER.md into the hermes-memory-zh fact
store so the L2 semantic-retrieval layer has a seed of structured facts.

Usage:
    python3 scripts/migrate_memory.py [--db PATH] [--memories DIR]
        [--model text-embedding-v4] [--base-url https://your-gateway/v1]
        [--api-key KEY]

Defaults resolve to the active HERMES_HOME; api-key falls back to the
DASHSCOPE_API_KEY / OPENAI_API_KEY env vars. Pass --api-key
"" to skip embedding (facts stored without vectors).
"""
import argparse
import os
import sys
from pathlib import Path

# --- resolve hermes home (defaults) ---------------------------------------
_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
_PROJ = Path(__file__).resolve().parent.parent

# Make the plugin's own modules importable (store.py / embedding.py).
sys.path.insert(0, str(_PROJ))
# hermes_state is imported lazily by store._init_db.
sys.path.insert(0, str(_HERMES_HOME / "hermes-agent"))


def split_entries(text: str) -> list[str]:
    """Split a MEMORY.md/USER.md body into individual entries on the § separator."""
    return [e.strip() for e in text.split("§") if e.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(_HERMES_HOME / "memory_store.db"))
    p.add_argument("--memories", default=str(_HERMES_HOME / "memories"))
    p.add_argument("--model", default="text-embedding-v4")
    p.add_argument("--base-url", default="https://your-gateway/v1")
    p.add_argument(
        "--api-key",
        default=(
            os.environ.get("DASHSCOPE_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", ""),
        ),
    )
    args = p.parse_args()

    from store import MemoryStore
    from embedding import EmbeddingClient

    client = None
    if args.api_key:
        client = EmbeddingClient(
            api_key=args.api_key, model=args.model, base_url=args.base_url, dim=1024
        )

    store = MemoryStore(db_path=args.db, embedding_client=client)
    memories = Path(args.memories)

    migrated = skipped = 0
    for fname, category in (("MEMORY.md", "general"), ("USER.md", "user_pref")):
        path = memories / fname
        if not path.exists():
            print(f"  - {fname}: not found, skipped")
            continue
        entries = split_entries(path.read_text(encoding="utf-8"))
        for entry in entries:
            try:
                store.add_fact(entry, category=category)
                migrated += 1
            except Exception as e:  # dedupe / transient — don't abort the run
                print(f"  ! skip: {entry[:40]!r} -> {e}")
                skipped += 1
        print(f"  {fname}: {len(entries)} entries -> {category}")

    total = store._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    print(f"\nMigrated {migrated} (skipped {skipped}). fact store now has {total} facts.")
    print(f"DB: {args.db}   embedding: {'ON' if client else 'OFF'}")


if __name__ == "__main__":
    main()
