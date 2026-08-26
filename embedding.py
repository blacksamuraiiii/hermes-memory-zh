# SPDX-License-Identifier: MIT
# hermes-memory-zh — Chinese semantic memory provider for Hermes Agent.
# Derived from the official holographic memory plugin (plugins/memory/holographic)
# in NousResearch/hermes-agent, original plugin by dusterbloom (PR #2351),
# Copyright (c) Nous Research. See LICENSE.
"""OpenAI-compatible embedding client for semantic retrieval.

Pointed at any OpenAI-compatible /v1/embeddings endpoint — configure `base_url`
to your gateway (e.g. DashScope compatible-mode or an internal AI gateway) and
pick a model like `text-embedding-v4` (1024-dim) or `bge-m3` (1024-dim).

Fully optional: if no API key is configured, or any call fails, `embed` returns
None and retrieval degrades to pure keyword/HRR search — it never raises.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


class EmbeddingClient:
    """Lazy OpenAI-compatible embedding client. Never raises on failure."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "text-embedding-v4",
        base_url: str = "https://your-gateway/v1",
        dim: int = 1024,
    ) -> None:
        self._api_key = api_key or ""
        self._model = model or "text-embedding-v4"
        self._base_url = base_url or None
        self._dim = int(dim or 1024)
        self._client = None

    @property
    def enabled(self) -> bool:
        """True when a key is present and the SDK is installed."""
        return bool(self._api_key) and _OPENAI_AVAILABLE

    def _ensure_client(self) -> None:
        if self._client is None:
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)

    def embed(self, text: str) -> Optional[bytes]:
        """Embed `text`, return float32 bytes (dim*4). None on any failure."""
        if not self.enabled or not text:
            return None
        try:
            self._ensure_client()
            resp = self._client.embeddings.create(
                model=self._model, input=text[:2000]
            )
            vec = np.array(resp.data[0].embedding, dtype=np.float32)
            return vec.tobytes()
        except Exception:
            return None

    def embed_array(self, text: str) -> Optional[np.ndarray]:
        """Embed `text`, return np.float32 array. None on any failure."""
        if not self.enabled or not text:
            return None
        try:
            self._ensure_client()
            resp = self._client.embeddings.create(
                model=self._model, input=text[:2000]
            )
            return np.array(resp.data[0].embedding, dtype=np.float32)
        except Exception:
            return None

    @staticmethod
    def from_bytes(data: bytes) -> np.ndarray:
        """Deserialize a stored float32 embedding back to a numpy array."""
        return np.frombuffer(data, dtype=np.float32)
