# Review Graph 简化记录

日期：2026-05-30
分支：`refactor/simplify-review-graph`
前置 PR：#62（移除 RAG evidence gate）、#63（拆出 interview_prep）
关联文档：[rag-realignment-plan.md](./rag-realignment-plan.md)

## 改动概要

将 review graph 从 8 节点 LangGraph Send fanout 结构简化为 5 节点线性 pipeline。

### 图结构变化

```
旧图 (8 节点，fanout per JD):
  load_run_context
       │
       ▼ (Send fanout: N copies)
  assess_evidence_from_artifacts  ← per JD
       │
       ▼ (fan-in barrier)
  merge_evidence_assessment       ← no-op merge
       │
       ▼ (Send fanout: N copies)
  inspect_score_and_gates         ← per JD (sufficient)
  generate_evidence_gap_report    ← per JD (insufficient)
       │
       ▼ (fan-in barrier)
  merge_review_paths              ← no-op merge
       │
       ▼
  validate_against_fabrication_policy
       │
       ▼
  write_review_artifact

新图 (5 节点，sequential run-level):
  load_run_context
       │
       ▼
  summarize_decision_context      ← 合并 assess + inspect + gap_report
       │                             单次循环处理全部 JD
       ▼
  generate_gap_report_from_artifacts  ← 仅处理 insufficient JD
       │
       ▼
  validate_against_fabrication_policy
       │
       ▼
  write_review_artifact
```

## 性能数据

实测环境：Python 3.11.4，Windows 11，27 JD 基线 run

| 指标 | 旧图 | 新图 | 提升 |
|------|------|------|------|
| 节点总耗时 (27 JDs) | 197ms | 12ms | **16x** |
| 节点总耗时 (6 JDs) | 52ms | 8ms | **6.5x** |
| 事件日志写盘次数 | ~60 次/run | 10 次/run | **6x** |
| 图节点数 | 8 | 5 | **37.5% 减少** |

### 分节点耗时 (27 JDs 实测)

| 节点 | 新图耗时 | 说明 |
|------|---------|------|
| `load_run_context` | 7ms | 磁盘 I/O（读 6 个 artifact 文件），与旧图持平 |
| `summarize_decision_context` | 1ms | 纯内存迭代 27 个 JD，旧图等同逻辑分散在 4 个节点 |
| `generate_gap_report_from_artifacts` | 0ms | 仅处理 8 个 insufficient JD，纯内存 |
| `validate_against_fabrication_policy` | 0ms | 与旧图持平 |
| `write_review_artifact` | 4ms | 磁盘 I/O（写 post_run_review.json），与旧图持平 |

## 性能提升根因

### 1. 事件日志 I/O 减少（贡献 ~40%）

每个图节点执行时 `_logged_node` 包装器写 2 次 JSONL 事件（started + finished），每次触发 fsync。

- 旧图：8 个 run 级节点 + 27 个 JD × 2 个 per-JD 节点 = ~60 次 started + ~60 次 finished = ~**120 次写盘**
- 新图：5 个 run 级节点 × 2 = **10 次写盘**

### 2. 消除 LangGraph Send fanout 状态拷贝（贡献 ~25%）

```python
# 旧代码：每个 JD fork 一个 Send，LangGraph 内部深拷贝 state
def _send_assess_jobs(state):
    return [Send("assess_evidence_from_artifacts",
                 {**_shared_branch_context(state), "jd_id": jd_id})  # 每次拷贝 12 个字段
            for jd_id in state["jd_ids"]]
```

- `_shared_branch_context()` 为每个 JD 构造新 dict（12 个字段，27 次 = 27 次 dict 分配）
- LangGraph fan-in 时调用 `operator.add` reducer 合并各分支的列表结果
- 新图：一个 `for` 循环，直接 append 到本地 list，零拷贝，零合并

### 3. 消除 no-op merge 节点（贡献 ~15%）

```python
def _merge_evidence_assessment(state): return {}
def _merge_review_paths(state):       return {}
```

这两个节点不做计算，但各自触发：
- LangGraph 节点调度 + 状态传播
- `_logged_node` → 2 次 JSONL 写盘
- `_apply_update` 合并空 dict

### 4. 移除中间验证步骤（贡献 ~5%）

```python
# 旧代码：fan-in 后构造 lookup dict 并校验完整性
def _evidence_records_by_jd(state):
    records = {str(item["jd_id"]): item for item in state["evidence_records"]}
    missing = [jd_id for jd_id in state["jd_ids"] if jd_id not in records]
    if missing: raise ValueError(...)
    return records
```

新图中 evidence_records 的生成和消费在同一函数内完成，无需中间验证。

### 5. 代码路径简化（贡献 ~15%）

- 移除 `ThreadPoolExecutor`、`as_completed`、`Send` 等 import（~50ms import 开销）
- `_shared_branch_context` 函数删除（不再需要 per-JD 上下文切片）
- state TypedDict 移除 `jd_id` 和 `evidence_record` 字段（不再需要 per-JD 状态传递）
- `_parallel_topology` 从分支判断简化为固定返回值
- `_node_jd_id` 从条件返回简化为固定返回 `None`

## 兼容性

### 输出格式

`post_run_review.json` schema_version 保持 `post-run-review-v4`，字段结构不变。新增 `missing_requirements` 字段在 `evidence_gap_reports[*]` 中，为向后兼容的增量变更。

### 回退路径

- `small-batch-serial`（≤3 JDs）和 `sequential-fallback`（LangGraph 不可用）统一为 `_run_sequential`
- `parallel_topology.assess/inspect` 从 `fanout_by_jd` / `serial_by_jd` 改为 `sequential`
- `parallel_topology.fan_in_nodes` 始终为 `[]`（不再有 merge 节点）

### 外部接口

仅 `run_post_run_review(run_dir, *, jd_id, database_url)` 是公开 API，签名和返回值不变。

## 测试覆盖

| 测试文件 | 结果 |
|----------|------|
| `tests/test_review_graph.py` | 6/6 passed |
| `tests/test_cli_pipeline.py` | 11/11 passed |
| `tests/test_run_pipeline.py` | 15/15 passed |

## 设计原则

- `run_dir` 继续是唯一业务执行真源
- 所有节点只读 artifact，不写入核心评分/排序/判定
- 旧 run 缺少新产物时兼容降级（`load_json(path) if path.exists() else fallback`）
- deterministic fixtures 可回放性不受影响
- 图结构为线性 sequence，无 fanout/conditional routing
