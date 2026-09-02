"""L1 dedup baseline：读 MEMORY.md/USER.md 建 token 基线，判定 L2 候选是否重复。"""
from __future__ import annotations
from pathlib import Path
from typing import List, Set

_ENTRY_DELIMITER = "§"

def build_baseline(memories_dir: str) -> List[Set[str]]:
    try:
        try:
            from .retrieval import FactRetriever  # 包上下文（真实运行时/pytest 包注册）
        except ImportError:
            from retrieval import FactRetriever    # 顶层 sys.path 兜底
        _tokenize = FactRetriever._tokenize
    except ImportError:
        import re
        def _tokenize(text: str) -> Set[str]:
            s = re.sub(r"\s+", "", text)
            return {s[i:i+2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())
    baseline: List[Set[str]] = []
    for name in ("MEMORY.md", "USER.md"):
        try:
            raw = (Path(memories_dir) / name).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for entry in raw.split(_ENTRY_DELIMITER):
            entry = entry.strip()
            if entry:
                tokens = _tokenize(entry)
                if tokens:
                    baseline.append(tokens)
    return baseline

def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def is_duplicate(fact_tokens: Set[str], baseline: List[Set[str]], threshold: float = 0.8) -> bool:
    if not fact_tokens or not baseline:
        return False
    return max(_jaccard(fact_tokens, b) for b in baseline) >= threshold
