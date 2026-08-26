# hermes-memory-zh

**Hermes Agent 中文语义记忆插件** —— 在官方 Holographic 记忆插件的基础上，叠加 jieba 中文分词与 embedding 语义检索，让中文记忆真正"搜得到、找得准"。

作为 Hermes 的**外部记忆提供者（L2）**运行，与内置的 MEMORY.md / USER.md（L1）**共存而非替换**。

---

## 为什么需要它

Hermes 内置的 Holographic 记忆插件用 SQLite FTS5 全文检索，但 FTS5 默认的 `unicode61` 分词器**不识别中文词边界**——整句中文被当成一个巨大 token 索引，导致：

- 存了「冰的黑咖啡」，搜「冰黑咖啡」返回零结果
- 中文自然语言查询召回率极差

`hermes-memory-zh` 从官方源码 fork，加入两样东西解决中文记忆检索：

1. **jieba 中文分词** —— 写入时把中文预切词存入独立的 FTS5 索引，检索按 AND → OR → 回退三步策略
2. **embedding 语义检索** —— 通过任意 OpenAI 兼容网关（如 DashScope 或自建 AI 网关）生成向量，语义相似度作为第 4 路打分信号

## 特性

- ✅ **jieba 中文分词** + tokenized FTS5 索引，中文 AND/OR/回退三步检索
- ✅ **embedding 语义检索**（默认 `text-embedding-v4`，可换 `bge-m3` 等），混合打分：FTS5(0.25) + Jaccard(0.15) + HRR(0.20) + Embedding(0.40)
- ✅ **FTS5 真实 rank** —— BM25 归一化到 [0,1]，不是硬编码常数
- ✅ **优雅降级** —— jieba / numpy / embedding 任一缺失都不崩，自动回退
- ✅ **config 全驱动** —— base_url / model / dim / weight 全部可配，零硬编码
- ✅ **独立插件** —— 装到 `~/.hermes/plugins/`，`hermes update` 不覆盖
- ✅ **与 L1 共存** —— MEMORY.md 继续每轮注入，本插件作为检索式 L2 叠加
- ✅ **MIT 许可** —— 继承官方，含完整版权声明

## 与官方方案的对比

|               | 官方 holographic | **hermes-memory-zh** |
| ------------- | ---------------- | -------------------------- |
| 中文分词      | ❌ 无            | ✅**jieba**          |
| 语义检索      | ❌               | ✅**embedding**      |
| 混合打分      | 3 信号           | ✅**4 信号**         |
| FTS rank      | 正确             | ✅**正确**           |
| 安装方式      | 内置             | ✅**独立插件**       |
| hermes update | 会重置           | ✅**不覆盖**         |

## 安装

```bash
# 从 Git 仓库安装（发布后）
hermes plugins install <owner>/hermes-memory-zh --enable

# 或手动放到插件目录
mkdir -p ~/.hermes/plugins/hermes-memory-zh
cp -r hermes_memory_zh/* ~/.hermes/plugins/hermes-memory-zh/

# 启用为记忆提供者
hermes config set memory.provider hermes-memory-zh

# 安装分词依赖（jieba 必需，openai 用于 embedding）
pip install jieba
```

重启 Hermes（`/restart` 或 `hermes gateway restart`），`hermes memory status` 确认插件已激活。

> 记忆按 L1/L2 分层：内置 MEMORY.md / USER.md 继续每轮注入，本插件作为 L2 提供大规模事实的语义检索，两者不冲突。

## 配置

在 `~/.hermes/config.yaml`：

```yaml
plugins:
  hermes-memory-zh:
    db_path: ~/.hermes/memory_store.db
    auto_extract: true
    default_trust: 0.5
    hrr_dim: 1024
    # —— 中文分词（装 jieba 即自动启用）——
    # —— 语义检索（OpenAI 兼容网关）——
    embedding_enabled: true
    embedding_model: text-embedding-v4   # 或 bge-m3 等（见下方"模型选择"）
    embedding_dim: 1024
    embedding_weight: 0.4
    openai_base_url: https://your-gateway/v1   # 填你的 OpenAI 兼容 embedding 网关
    openai_api_key: ""                          # 留空则从环境变量取
```

`openai_api_key` 为空时，依次尝试环境变量 `DASHSCOPE_API_KEY`、`OPENAI_API_KEY`（或你网关约定的 key 环境变量）。设置 `embedding_enabled: false` 可关闭语义检索，退化为纯本地关键词检索。

## Embedding 模型选择

插件**不绑定某个特定 embedding 模型**——只要你的网关暴露 OpenAI 兼容的 `/v1/embeddings` 端点，改 `embedding_model`（和必要时 `embedding_dim`）即可。常用选项：

| 模型                       | 维度                          | 特点                                                                  | 典型来源                          |
| -------------------------- | ----------------------------- | --------------------------------------------------------------------- | --------------------------------- |
| `text-embedding-v4`      | 64~2048 可自定义（默认 1024） | 通义（Qwen3）多语言统一向量模型，检索/聚类/分类强，较 v3 提升 15%~40% | DashScope 兼容模式                |
| `bge-m3`                 | 1024                          | 多语言（100+）、开源主流、社区验证多                                  | DashScope / 各类 AI 网关 / 自部署 |
| `text-embedding-3-small` | 1536                          | OpenAI 官方                                                           | OpenAI                            |

**推荐**：中文为主的记忆，`text-embedding-v4` 和 `bge-m3` 都是好选择，二选一即可——具体看你的网关对哪个模型开放了额度。切换只需改 config 的 `embedding_model`（若维度不同，同步改 `embedding_dim`），**但换模型后旧 facts 的向量需重新生成**（跑 `scripts/migrate_memory.py` 或单独 backfill）。

> ⚠️ 换模型即换向量空间：新旧 embedding 不可混用，切换后请对已有 facts 重新生成向量。

## 原理

```
写入：中文内容 → jieba 分词 → 存入 facts.content_tokens
      → 生成 embedding 向量 → 存入 facts.embedding

检索：中文查询 → jieba 分词
      → Step1 tokenized AND（全词命中，最精确）
      → Step2 tokenized OR（任一词命中，更宽）
      → Step3 回退 unicode61（英文/无 jieba）
      → 混合打分重排：FTS5 + Jaccard + HRR + Embedding
```

## 致谢

本项目基于以下开源工作，特此致谢：

- **[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)** —— 本项目 fork 自其内置的 **Holographic Memory Provider**（`plugins/memory/holographic`），由 **dusterbloom** 于 PR #2351 贡献，后适配到 MemoryProvider ABC。底层 store / retrieval / HRR 实现均源自此，版权归 Nous Research。
- **[Songokou1983/holographic-zh](https://github.com/Songokou1983/holographic-zh)** —— 提供 jieba 中文分词 + OpenAI embedding 语义检索的思路参考。本项目的混合打分与降级设计受其启发，并修复了其 `fts_rank` 被硬编码为 0.5 的缺陷。
- **[kyan001/Holographic-CHS-for-Hermes](https://github.com/kyan001/Holographic-CHS-for-Hermes)** —— 提供中文 FTS5（trigram）与「独立插件、不覆盖官方文件」的安装/分发思路参考。

三者均为 MIT 许可。本项目保留了官方源码的版权声明，详见 [LICENSE](LICENSE)。

## LICENSE

[MIT](LICENSE)
