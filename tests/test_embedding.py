"""Tests for EmbeddingClient (OpenAI-compatible gateway)."""
import numpy as np

from embedding import EmbeddingClient


class _FakeData:
    embedding = [0.1] * 1024


class _FakeEmb:
    def create(self, **kwargs):
        self.last = kwargs
        return type("R", (), {"data": [_FakeData()]})()


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.embeddings = _FakeEmb()


def test_disabled_without_key():
    c = EmbeddingClient(api_key="")
    assert not c.enabled
    assert c.embed("text") is None
    assert c.embed_array("text") is None


def test_embed_returns_float32_bytes(monkeypatch):
    import embedding as emb_mod
    fake = _FakeOpenAI()

    def make(**kw):
        fake.kwargs = kw
        return fake

    monkeypatch.setattr(emb_mod, "OpenAI", make)
    monkeypatch.setattr(emb_mod, "_OPENAI_AVAILABLE", True)

    c = EmbeddingClient(api_key="k", model="bge-m3", base_url="https://test-gateway/v1", dim=1024)
    assert c.enabled
    b = c.embed("示例公司人工智能研发")
    assert b and len(b) == 1024 * 4  # dim * float32

    # base_url/model forwarded to the SDK
    assert fake.kwargs["base_url"] == "https://test-gateway/v1"
    assert fake.embeddings.last["model"] == "bge-m3"


def test_embed_array_shape(monkeypatch):
    import embedding as emb_mod
    monkeypatch.setattr(emb_mod, "OpenAI", lambda **kw: _FakeOpenAI())
    monkeypatch.setattr(emb_mod, "_OPENAI_AVAILABLE", True)

    c = EmbeddingClient(api_key="k", dim=1024)
    arr = c.embed_array("中文测试")
    assert arr.shape == (1024,)
    assert arr.dtype == np.float32


def test_from_bytes_roundtrip():
    vec = np.ones(1024, dtype=np.float32)
    back = EmbeddingClient.from_bytes(vec.tobytes())
    assert back.shape == (1024,)
    assert np.array_equal(back, vec)
