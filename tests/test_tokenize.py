"""Tests for jieba Chinese tokenization helpers in store.py."""
import pytest

from store import _JIEBA_AVAILABLE, _tokenize_chinese, _tokenize_query


@pytest.mark.skipif(not _JIEBA_AVAILABLE, reason="jieba not installed")
def test_chinese_tokenize_segments():
    out = _tokenize_chinese("示例公司人工智能研发中心建设项目")
    assert out and " " in out  # 应被切成多个词
    assert "人工智能" in out.split()


@pytest.mark.skipif(not _JIEBA_AVAILABLE, reason="jieba not installed")
def test_tokenize_query_and_mode():
    q = _tokenize_query("人工智能研发", mode="AND")
    assert q and " " in q  # AND: FTS5 空格连接
    qo = _tokenize_query("人工智能研发", mode="OR")
    assert " OR " in qo  # OR: 显式 OR


def test_tokenize_empty_on_missing_jieba(monkeypatch):
    monkeypatch.setattr("store._JIEBA_AVAILABLE", False)
    monkeypatch.setattr("store._jieba", None)
    assert _tokenize_chinese("示例公司") == ""
    assert _tokenize_query("示例公司") == ""
    assert _tokenize_chinese("") == ""
