from store import MemoryStore

def test_consolidate_merges_duplicates(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "t.db"))
    s.add_fact("示例用户 示例城市 项目负责人 分管研发 负责平台研发", category="general")
    id_b = s.add_fact("示例用户 示例城市 项目 负责人 分管研发 平台 研发", category="general")
    s.update_fact(id_b, trust_delta=-0.2)   # 制造信任悬殊 0.5 vs 0.3
    r = s.consolidate_similar(threshold=0.8)  # jieba 实算两两 Jaccard=0.800
    assert r["removed_ids"]
    assert len(s.list_facts(limit=100)) == 1
    s.close()

def test_consolidate_keeps_distinct(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "t.db"))
    s.add_fact("示例用户 示例城市 项目 负责人", category="general")
    s.add_fact("示例 数据 计划 部署 测试 环境", category="general")   # 实算 Jaccard=0
    r = s.consolidate_similar(threshold=0.8)
    assert not r["removed_ids"]
    s.close()
