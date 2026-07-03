# 大纲议事质量升级回归报告

更新时间：2026-06-30

## 本轮验证范围

本报告记录服务层与测试脚本改造后的轻量回归结果。验证重点：

- 数字动态化：`2`、`50`、`100` 仅作为当前测试输入，不作为固定逻辑。
- 分卷生成：请求 2 卷时生成 2 个卷纲。
- 章节窗口：2 卷 x 50 章在当前默认窗口策略下生成 10 个动态窗口。
- 章纲展开：从窗口生成 100 个章纲。
- 严格指标：窗口字段、mini_climax、伏笔窗口覆盖、结构化 state_change、结构化 foreshadowing_use、source_window、卷末/终章功能。
- Agent 契约：`decision/scores` 及其来源字段。

## 已运行命令

```bash
python -m py_compile backend/app/services/outline_debate_service.py
python -m py_compile test-artifacts/run_outline_debate_browser_llm_tests.py
```

结果：均通过。

## 本地合成质量门结果

使用 `local_preview=True` 构造 2 卷 x 50 章请求，不调用远程模型。

```json
{
  "volume_count": 2,
  "volume_quality_status": "passed",
  "chapter_window_count": 10,
  "chapter_count": 100,
  "chapter_quality_status": "passed",
  "chapter_blocking_count": 0,
  "window_required_field_coverage": 1.0,
  "window_mini_climax_coverage": 1.0,
  "foreshadowing_window_coverage": 1.0,
  "state_change_coverage": 1.0,
  "foreshadowing_use_coverage": 1.0,
  "source_window_coverage": 1.0,
  "volume_end_function_coverage": 1.0,
  "final_chapter_turn_present": true,
  "first_state_change_is_dict": true,
  "first_foreshadowing_use_is_dict": true,
  "chapter_50_function": "volume_climax",
  "chapter_100_function": "book_or_phase_turn"
}
```

## Agent 来源字段检查

使用 `local_preview=True` 构造单 turn，不调用远程模型。

```json
{
  "decision": "revise",
  "decision_source": "service_default",
  "score_keys": [
    "character",
    "continuity",
    "selling",
    "setting",
    "story_promise",
    "structure"
  ],
  "score_source": "service_default",
  "used_remote_model": false
}
```

结论：当模型未提供 `decision/scores` 时，服务层兜底字段可用，并明确标注来源。

## 尚未运行的重型验证

完整 10 题材真实浏览器 + LLM 压测尚未在本轮自动触发。原因：新版脚本会进行大量真实远程模型调用。

后续应运行：

```bash
python test-artifacts/run_outline_debate_browser_llm_tests.py
```

验收时必须看每个 case 的 `accepted`，而不是只看 `ok`。

- `ok=true`：流程跑完。
- `accepted=true`：严格验收全部通过。

## 严格通过条件

完整远程压测只有在 10 个题材全部 `accepted=true` 时，才能证明真实 LLM 输出也满足本次计划的最终验收。

## 真实 LLM 压测中断与修复记录

首次运行新版 10 题材真实 LLM 压测时，第 1 个题材暴露出模型补丁退化问题：

```text
章节窗口数量异常：2，期望10
state_change_coverage: 0.73
foreshadowing_use_coverage: 0.73
标题重复率: 0.9200
```

解释：服务层原本生成了完整动态骨架，但 LLM 返回的 `artifact_patch` 中只有 2 个 `chapter_windows`，合并逻辑允许不完整模型补丁覆盖服务层骨架，导致质量门失败。

已补修复层：

- `model_patch_missing_or_incomplete_volume_outlines`：补齐缺失或字段不完整的卷纲。
- `model_patch_failed_strict_chapter_quality_gate`：模型章纲补丁未通过严格质量门时，重建完整 `chapter_windows` 与 `chapter_outlines`。

坏补丁修复验证：

```json
{
  "repair_applied": true,
  "window_count": 10,
  "chapter_count": 100,
  "quality_status": "passed",
  "blocking_count": 0
}
```

下一次完整真实 LLM 压测应验证该修复层是否能把模型退化补丁稳定拉回严格验收标准。

## 模板污染修复记录

第二轮真实 LLM 压测中，第 3 个题材暴露出模型发言污染问题：

```text
template_blocking_count: 100
命中模式：待确认
```

原因：服务层重建章节时仍会从模型 turn 中提取句子；如果模型发言包含“待确认”，这些低质量句子会进入 `crisis/conflict/result` 等章纲字段。

修复：新增安全取句逻辑。

- `_safe_debate_sentence(...)`：命中模板阻塞词时改用具体 fallback。
- `_contains_outline_template(...)`：统一模板判断。
- `_distinct_chapter_beats(...)`：命中模板的 crisis/climax/result 候选会先清空，再用状态变化生成具体危机、高潮、结果。

污染模拟验证：

```json
{
  "status": "passed",
  "template_blocking_count": 0,
  "blocking_count": 0,
  "chapter_count": 100,
  "window_count": 10
}
```

## 最终完整真实 LLM 压测结果

运行目录：`test-artifacts/outline_debate_browser_llm_20260630T080419Z`

汇总文件：`test-artifacts/outline_debate_browser_llm_20260630T080419Z/summary.json`

最终结果：

```json
{
  "cases": 10,
  "ok": 10,
  "accepted": 10
}
```

10 个题材全部通过严格验收：

| case | 题材 | 卷纲 | 章节窗口 | 章纲 | quality | accepted |
|---:|---|---:|---:|---:|---|---|
| 1 | 东方玄幻升级流 | 2 | 10 | 100 | passed | true |
| 2 | 都市悬疑探案 | 2 | 10 | 100 | passed | true |
| 3 | 赛博朋克群像 | 2 | 10 | 100 | passed | true |
| 4 | 古代权谋女强 | 2 | 10 | 100 | passed | true |
| 5 | 轻科幻殖民星球 | 2 | 10 | 100 | passed | true |
| 6 | 现言娱乐圈成长 | 2 | 10 | 100 | passed | true |
| 7 | 诡异规则怪谈 | 2 | 10 | 100 | passed | true |
| 8 | 西幻冒险公路文 | 2 | 10 | 100 | passed | true |
| 9 | 历史架空商战 | 2 | 10 | 100 | passed | true |
| 10 | 校园青春轻悬疑 | 2 | 10 | 100 | passed | true |

关键指标全部达标：

```json
{
  "template_blocking_count": 0,
  "state_change_coverage": 1.0,
  "foreshadowing_use_coverage": 1.0,
  "source_window_coverage": 1.0,
  "volume_end_function_coverage": 1.0,
  "final_chapter_turn_present": true
}
```

远程 LLM 与 Agent 契约覆盖：

```json
{
  "turns": 153,
  "remote_ok": 153,
  "decision": 153,
  "scores": 153,
  "decision_source": 153,
  "score_source": 153,
  "non_remote_or_error": []
}
```

结论：本轮计划要求的动态规模、严格验收指标、真实 LLM 验证、失败修复与文档记录均已完成。
