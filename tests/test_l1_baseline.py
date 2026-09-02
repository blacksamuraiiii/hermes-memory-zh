from l1_baseline import build_baseline, is_duplicate

def test_build_baseline_splits_by_delimiter(tmp_path):
    (tmp_path / "MEMORY.md").write_text("项目规范：配置文件不入仓库\n§\n日志脱敏后再提交\n", encoding="utf-8")
    baseline = build_baseline(str(tmp_path))
    assert len(baseline) == 2
    assert all(isinstance(t, set) and t for t in baseline)

def test_is_duplicate_high_overlap():
    base = {"配置", "规范", "文档", "仓库", "脱敏"}
    fact = {"配置", "规范", "文档", "仓库", "脱敏", "测试"}
    assert is_duplicate(fact, [base], threshold=0.8) is True

def test_is_duplicate_boundary_exact():
    base = {"配置", "规范", "文档", "仓库"}
    fact = {"配置", "规范", "文档", "仓库", "评审"}
    assert is_duplicate(fact, [base], threshold=0.8) is True

def test_is_duplicate_low_overlap():
    base = {"技能", "路由"}
    fact = {"发布", "版本", "回归", "验证"}
    assert is_duplicate(fact, [base], threshold=0.8) is False

def test_is_duplicate_max_over_entries():
    base_a = {"技能", "路由"}
    base_b = {"配置", "规范", "文档", "仓库"}
    fact = {"配置", "规范", "文档", "仓库", "评审"}
    assert is_duplicate(fact, [base_a, base_b], threshold=0.8) is True
