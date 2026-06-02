# RAG Reranker 降级分析 - 2026-06-02

## 背景

本轮目标是验证一个假设：当前 golden set 中其他指标已经较好，MRR 明显偏低，是否主要因为仍使用纯 BM25、缺少 reranker。

实验分支：

`codex/p0-reranker-mrr-closure`

复用 clean baseline run：

`baseline/runs-formal-20260601/baseline-formal-r3-full-raw-library-clean-20260601`

评估输出：

`baseline/p0-reranker-mrr-closure-20260602/`

## 实验结果

| 配置 | MRR | P@1 | R@10 | weighted R@10 | all expected hit | all primary hit | top1 | top3 | top10 | miss |
|------|----:|----:|-----:|--------------:|-----------------:|----------------:|-----:|-----:|------:|-----:|
| BM25 baseline | 0.474 | 0.240 | 0.920 | 0.910 | 0.84 | 0.88 | 6 | 15 | 25 | 0 |
| BM25@10 -> reranker | 0.415 | 0.200 | 0.920 | 0.910 | 0.84 | 0.88 | 5 | 14 | 25 | 0 |
| BM25@20 -> reranker | 0.387 | 0.200 | 0.820 | 0.800 | 0.76 | 0.76 | 5 | 12 | 22 | 3 |

`BM25@50 -> reranker` 曾启动，但运行超过 3 分钟后被人工中断，未生成完整报告，因此不纳入本轮结论。

## 直接结论

MRR 短板确实主要是排序问题，而不是召回问题。

BM25 baseline 中，25 条 answerable query 至少都有一个相关文档进入 top10，但只有 6 条 top1、15 条 top3。也就是说，相关文档基本能被召回，但排得不够靠前。

但是，“直接加 cross-encoder reranker”并没有解决问题，反而降低了质量：

- BM25@10 -> reranker：MRR 从 `0.474` 降到 `0.415`。
- BM25@20 -> reranker：MRR 进一步降到 `0.387`，并出现 3 条 top10 miss。
- first-stage limit 越大，reranker 过度重排和引入噪声的风险越高。

## 降级原因：项目文本类型不适合纯语义重排

### 1. Golden 需要 artifact 精确命中，但 reranker 只看自然语言文本

当前 golden set 评估的是 chunk/source_id 级别命中，例如：

- `jd-024:ranking`
- `jd-027-req-013`
- `jd-016-req-005`
- `candidate-profile`

BM25 对 artifact id、source_id、query 中的检索关键词很敏感。Cross-encoder reranker 只看 `(query, candidate.text)`，不会天然理解 `jd-024:ranking` 这类 label 是一个精确目标。

所以当 query 中包含 `final_score`、`decision_source`、`rewrite_cost`、`jd-024:ranking` 这类评测用关键词时，BM25 能利用它们，reranker 反而会按自然语义把相似但错误的 artifact 推上来。

### 2. `requirement_evidence` 文本短、模板化、区分度弱

很多 requirement chunk 形态类似：

```text
[AI Engineer (MTS) | python, product collaboration, llm]
Bachelor of Engineering | Bachelor of Science | Master of Al | ...
missing
```

或：

```text
[Technical Support Engineer ... | python, product collaboration, llm]
Strong written communication and ability to explain technical tradeoffs clearly.
missing
```

这些文本对 cross-encoder 来说语义区分度不高。大量 chunk 都共享 JD prefix、keywords 和 `missing` 状态，真正能区别 expected label 的细节很少。

结果是：reranker 会在同一个 JD 的多个 requirement 之间重新洗牌，把 BM25 已经排到前面的 expected requirement 往后推。

### 3. `ranking_explanation` 文本高度重复

`ranking_explanation` chunk 包含很多机器生成字段：

```text
Deterministic LLM-assessment fallback based on rule score 0.96.
final_score=0.99
decision_source=v0.5.7-requirement-score
rule_fit=0.99
keyword_coverage=0.99
rule_evidence=0.99
rewrite_cost=0.51
```

不同 JD 的 ranking explanation 文本结构非常相似。BM25 可以靠 source_id 或 query hint 命中 `jd-024:ranking`；reranker 则会觉得多个 ranking chunk 都差不多相关。

典型降级：

- `rag-golden-027`
- expected：`candidate-profile`, `jd-024:ranking`
- BM25：`jd-024:ranking` rank 1
- reranker：`jd-024:ranking` 掉出 top10

### 4. 长文本 `jd_input` / `jd_description` 容易骗过 reranker

对 `rag-golden-030`，expected 是细粒度 requirement：

```text
jd-027-req-013
用 AI 构建产品，而不是只写业务代码。
```

但 reranker 把长 `jd_input` 排到第一，因为 JD input 中包含大量自然语言和技术词：

```text
AI Automation
Multi-Agent
Python
FastAPI
Vector Database
Embedding
AI agents
evaluation harness
```

从语义模型角度，长 JD input 看起来很相关；但从评测角度，它不是目标 evidence artifact，也不能替代 requirement evidence。

### 5. 语料混合了多种非自然文档

当前 corpus 不是普通问答语料，而是混合了：

- 中文 query
- 英文 JD / requirement
- OCR 断字或空格污染
- `missing` / `verified` 状态
- `final_score` / `rule_fit` / `decision_source` 等机器字段
- source_id 依赖型 label
- JD context prefix

这类文本不完全符合 cross-encoder 常见训练分布。模型更容易按“自然语言表面相关性”排序，而不是按 artifact provenance、source_type 和 expected label 精确性排序。

## 典型负向样本

| Query | BM25 首个相关 rank | Reranker 首个相关 rank | 现象 |
|-------|-------------------:|-----------------------:|------|
| `rag-golden-001` | 3 | miss | expected requirement 被同 JD 其他 requirement 挤出 top10 |
| `rag-golden-006` | 3 | 7 | 同 JD requirement 重新排序后 expected 后移 |
| `rag-golden-012` | 2 | 7 | expected 原本靠前，reranker 后移 |
| `rag-golden-016` | 6 | miss | expected requirement 被排出 top10 |
| `rag-golden-027` | 1 | miss | `jd-024:ranking` 被其他 ranking explanation 挤出 |
| `rag-golden-030` | 1 | 3 | 长 `jd_input` / `jd_description` 被推到前面 |

## 结论

当前问题不是“reranker 不该用”，而是不能让 reranker 完全接管排序。

更准确的判断是：

1. BM25 负责精确定位 artifact 的能力仍然很重要。
2. cross-encoder reranker 可以作为辅助语义信号，但不能覆盖 BM25/source_id/source_type/role 信号。
3. 直接替换式 rerank 会破坏当前 golden 需要的精确 artifact 命中。
4. first-stage limit 越大，纯 reranker 引入的泛相关噪声越多。

## 后续建议

### P0：改为融合式 reranking，而不是替换式 reranking

建议使用：

```text
final_score =
  bm25_score * strong_weight
  + reranker_score * small_weight
  + source_type_weight
  + role_or_query_intent_weight
  + exact_artifact_hint_boost
```

关键点：

- 保留 BM25 排序/分数作为强先验。
- reranker 只做小幅调序。
- 对 `requirement_evidence`、`gap_map`、`ranking_explanation` 做 source-type 权重。
- 对包含 artifact id / label hint 的 query 增加 exact match boost。
- 先用 `first-stage-limit=10` 观察，避免候选噪声过多。

### P1：降低同质化 chunk 对 reranker 的干扰

可考虑：

- 将 JD context prefix 与 requirement_text 分字段，而不是拼成同一段文本。
- reranker 输入只使用核心 evidence text，减少 `missing`、`final_score`、`rule_fit` 等机器字段干扰。
- 对 `ranking_explanation` 增加更明确的 JD/source 标识文本，但不要只依赖 source_id。

### P2：引入 graded relevance

当前 MRR 是严格 label-level 评价。对宽问题，可以允许多个 acceptable documents，避免把语义上可用但非 expected label 的文档全部计为 0。

这不是为了掩盖 reranker 问题，而是让宽问题的评价更接近真实使用场景。

## 复现命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_golden_rag_set.py fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\p0-reranker-mrr-closure-20260602\bm25-baseline.json --retriever-mode bm25

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\p0-reranker-mrr-closure-20260602\reranker-bm25-fs10.json --retriever-mode bm25 --reranker BAAI/bge-reranker-v2-m3 --first-stage-limit 10

.\.venv\Scripts\python.exe scripts\evaluate_rag_layers.py --layer retriever --golden-file fixtures\golden_rag_questions.json --run-dir baseline\runs-formal-20260601\baseline-formal-r3-full-raw-library-clean-20260601 --output baseline\p0-reranker-mrr-closure-20260602\reranker-bm25-fs20.json --retriever-mode bm25 --reranker BAAI/bge-reranker-v2-m3 --first-stage-limit 20
```
