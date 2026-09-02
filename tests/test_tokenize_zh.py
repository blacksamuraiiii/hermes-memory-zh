from retrieval import FactRetriever

def test_tokenize_chinese_text():
    tokens = FactRetriever._tokenize("示例城市项目负责人分管研发")
    assert len(tokens) > 1
    assert any(len(t) <= 4 for t in tokens)

def test_tokenize_mixed_text():
    tokens = FactRetriever._tokenize("项目规范 sample-project 统一入口")
    assert any(t.isalpha() and ord(t[0]) > 127 for t in tokens)
    assert any(t.isalpha() and ord(t[0]) < 128 for t in tokens)
