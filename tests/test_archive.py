from store import MemoryStore
from retrieval import FactRetriever

def test_archive_stale_and_filter(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "t.db"))
    stale = s.add_fact("旧项目 废弃 配置", category="general")
    fresh = s.add_fact("当前 项目 分管 研发", category="general")
    up = s.add_fact("用户偏好 永不归档", category="user_pref")
    s.update_fact(stale, trust_delta=-0.3)
    s.update_fact(up, trust_delta=-0.3)
    r = s.archive_stale(min_trust=0.35, max_retrieval=2, max_age_days=0)
    assert stale in r["archived_ids"]
    assert fresh not in r["archived_ids"]
    assert up not in r["archived_ids"]      # user_pref 永不归档
    fr = FactRetriever(store=s)
    assert all(x["content"] != "旧项目 废弃 配置" for x in fr.search("旧项目"))
    s.close()

def test_restore_archived(tmp_path):
    s = MemoryStore(db_path=str(tmp_path / "t.db"))
    fid = s.add_fact("某 临时 记录", category="general")
    s.update_fact(fid, trust_delta=-0.3)
    s.archive_stale(min_trust=0.35, max_retrieval=2, max_age_days=0)
    assert s.list_facts(archived_only=True)[0]["fact_id"] == fid  # 归档中
    assert s.restore_archived(fid) is True
    assert s.list_facts(archived_only=True) == []                  # 已反归档
    assert s.list_facts(limit=10)[0]["fact_id"] == fid             # 回到活跃
    s.close()
