import json

from hermes_memory_zh_test import HermesMemoryZhProvider


def _provider(tmp_path):
    p = HermesMemoryZhProvider(config={"db_path": str(tmp_path / "m.db")})
    p.initialize("test")
    return p


def test_consolidate_action(tmp_path):
    p = _provider(tmp_path)
    out = p.handle_tool_call("fact_store", {"action": "consolidate"})
    d = json.loads(out)
    assert "merged_pairs" in d and "removed_ids" in d


def test_archive_action(tmp_path):
    p = _provider(tmp_path)
    out = p.handle_tool_call("fact_store", {"action": "archive"})
    d = json.loads(out)
    assert "archived_ids" in d


def test_list_archived_action(tmp_path):
    p = _provider(tmp_path)
    out = p.handle_tool_call("fact_store", {"action": "list_archived"})
    d = json.loads(out)
    assert "facts" in d and "count" in d


def test_restore_action(tmp_path):
    p = _provider(tmp_path)
    out = p.handle_tool_call(
        "fact_store", {"action": "restore", "fact_id": 1})
    d = json.loads(out)
    assert "restored" in d
