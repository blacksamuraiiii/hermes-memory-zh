"""Tests for FactRetriever hybrid scoring and FTS-rank correctness."""
import numpy as np
import pytest

from store import MemoryStore
from retrieval import FactRetriever


def _store(tmp_path):
    return MemoryStore(db_path=tmp_path / "m.db")


def test_weight_allocation_without_client(tmp_path):
    s = _store(tmp_path)
    r = FactRetriever(s, embedding_weight=0.4, embedding_client=None)
    assert r.embedding_weight == 0.0  # no usable client → signal dropped
    assert r.fts_weight > 0  # local signals kept


class _FakeClient:
    enabled = True

    def embed_array(self, text):
        return np.ones(1024, dtype=np.float32)


def test_weight_allocation_with_client(tmp_path):
    s = _store(tmp_path)
    r = FactRetriever(s, embedding_weight=0.4, embedding_client=_FakeClient())
    assert r.embedding_weight == 0.4
    assert r.fts_weight == 0.25  # rebalanced to 4-signal hybrid


def test_fts_rank_is_real_normalized(tmp_path):
    """The FTS5 rank signal must be the real normalized BM25 rank, not a
    hardcoded constant — the exact bug that made holographic-zh a half-finished
    fork (fts_rank was pinned to 0.5)."""
    s = _store(tmp_path)
    s.add_fact("示例公司人工智能研发中心建设项目", category="project")
    s.add_fact("示例公司市场部客户服务方案", category="project")
    s.add_fact("研发部内部工具开发进度", category="project")

    r = FactRetriever(s)
    res = r.search("人工智能", limit=10)
    assert res
    ranks = [x["fts_rank"] for x in res]
    # best match normalized to 1.0 (a hardcoded constant would fail this)
    assert max(ranks) == pytest.approx(1.0)
    assert 0.0 <= min(ranks) <= 1.0
    assert "人工智能" in res[0]["content"]


def test_search_with_embedding_reranks(tmp_path, monkeypatch):
    s = _store(tmp_path)
    s.add_fact("示例公司人工智能研发中心建设项目", category="project")

    # Fake client returns a constant vector — embedding participates but
    # doesn't crash; search still returns the fact.
    r = FactRetriever(s, embedding_weight=0.4, embedding_client=_FakeClient())
    res = r.search("人工智能", limit=10)
    assert res and "人工智能" in res[0]["content"]
    assert "score" in res[0]
