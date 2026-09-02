from store import MemoryStore

def test_archived_column_exists(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "t.db"))
    cols = [r[1] for r in s._conn.execute("PRAGMA table_info(facts)")]
    assert "archived" in cols
    s.close()
