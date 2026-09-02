from hermes_memory_zh_test import HermesMemoryZhProvider

def _make_provider(tmp_path, memory_dir):
    p = HermesMemoryZhProvider(config={"db_path": str(tmp_path / "mem.db")})
    # _hermes_home 是 hermes 根目录（真实运行时 = get_hermes_home()），
    # prefetch 内部拼 self._hermes_home + "/memories"，故这里传 memories 目录的父目录
    p._hermes_home = str(memory_dir.parent if memory_dir.name == "memories" else memory_dir)
    class FakeRetriever:
        def search(self, query, min_trust=0.0, limit=5):
            return [
                {"trust_score": 0.9, "content": "日志级别 配置 按环境"},
                {"trust_score": 0.9, "content": "发布流程 审批 走审批平台"},
            ]
    p._retriever = FakeRetriever()
    p._min_trust = 0.0
    return p

def test_prefetch_filters_l1_duplicate(tmp_path):
    memory_dir = tmp_path / "memories"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "项目规范：构建脚本统一入口\n§\n日志级别按环境配置\n", encoding="utf-8")
    p = _make_provider(tmp_path, memory_dir)
    out = p.prefetch("项目规范 日志级别")
    assert "发布流程" in out
    assert "日志级别" not in out

def test_prefetch_fallback_without_l1(tmp_path):
    p = _make_provider(tmp_path, tmp_path)
    out = p.prefetch("日志级别")
    assert "日志级别" in out
