"""Tests for MemoryStore fact storage + Chinese-aware search."""
import pytest

from store import MemoryStore, _JIEBA_AVAILABLE


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(db_path=tmp_path / "mem.db")
    yield s
    s.close()


def test_add_and_dedupe(store):
    fid1 = store.add_fact("示例公司人工智能研发中心建设项目", category="project")
    fid2 = store.add_fact("示例公司人工智能研发中心建设项目", category="project")
    assert fid1 == fid2  # UNIQUE content → same id
    assert len(store.search_facts("人工智能")) >= 1


@pytest.mark.skipif(not _JIEBA_AVAILABLE, reason="jieba not installed")
def test_chinese_search_matches_tokenized(store):
    store.add_fact("示例公司人工智能研发中心建设项目与优化", category="project")
    store.add_fact("示例公司市场部客户服务方案", category="project")

    # 中文查询应命中 tokenized 索引
    r = store.search_facts("人工智能")
    assert r, "expected a chinese match"
    assert "人工智能" in r[0]["content"]


@pytest.mark.skipif(not _JIEBA_AVAILABLE, reason="jieba not installed")
def test_search_fallback_to_english(store):
    store.add_fact("The deploy process for the project", category="general")
    r = store.search_facts("deploy process")
    assert r and "deploy" in r[0]["content"]


def test_update_fact_keeps_tokens_in_sync(store):
    fid = store.add_fact("示例公司人工智能模型优化", category="project")
    store.update_fact(fid, content="示例公司市场部服务效率提升")
    r = store.search_facts("服务效率")
    assert r and r[0]["fact_id"] == fid
