# Prompt Agent Lifecycle Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose six lifecycle-oriented prompt-agent workflows in `/api/workflows` and make the Agent menu default to those workflows while preserving the existing prompt-library lanes as an advanced view.

**Architecture:** Keep the existing 32 `prompt_agent` contracts as the source of truth. Add lifecycle workflow definitions in `backend/app/agents/shared/prompt_catalog.py`, generate nodes from the existing `_prompt_workflow_node()` helper, and annotate workflow metadata so the frontend can distinguish lifecycle workflows from legacy prompt-library workflows. Update frontend type contracts and `AgentsPage` filtering so lifecycle workflows appear first and the old five prompt lanes remain available for debugging.

**Tech Stack:** Python 3.13, FastAPI service layer, Pydantic workflow schema payloads, React 19, TypeScript, Ant Design, ECharts, Node test runner, pytest.

---

## File Structure

- Modify `backend/app/agents/shared/prompt_catalog.py`
  - Add `PromptLifecycleWorkflowDefinition`.
  - Add `PROMPT_LIFECYCLE_WORKFLOWS`.
  - Add `list_prompt_lifecycle_workflows()`.
  - Add support for semantic edges, workflow kind, trigger policy, and shortcut flags.

- Modify `backend/app/services/studio_service.py`
  - Include lifecycle workflows in `StudioService.list_workflows()`.
  - Keep legacy prompt workflows in the response as `workflow_kind="prompt_library"` for advanced/debug view.
  - Apply existing runtime metadata and model config annotation to both workflow sets.

- Modify `backend/tests/test_prompt_catalog.py`
  - Add lifecycle workflow contract tests.
  - Keep legacy prompt workflow coverage.

- Modify `backend/tests/test_agent_prompt_runtime_contract.py`
  - Add API-level test proving `/api/workflows` exposes lifecycle workflows and keeps model config metadata.

- Modify `frontend/src/types/api.ts`
  - Add `workflow_kind`, `trigger_policy`, and optional node tags to workflow interfaces.

- Modify `frontend/src/pages/AgentsPage.tsx`
  - Default selected workflow to `chapter_closed_loop_lifecycle`.
  - Sort lifecycle workflows before runtime and legacy prompt-library views.
  - Label shortcut workflows/nodes and advanced prompt-library workflows.

- Modify `frontend/tests/agents-page-contract.test.mjs`
  - Add static contract tests for lifecycle default, workflow kind labels, and legacy prompt-library availability.

---

### Task 1: Backend Tests For Lifecycle Workflow Catalog

**Files:**
- Modify: `backend/tests/test_prompt_catalog.py`
- Later Modify: `backend/app/agents/shared/prompt_catalog.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `backend/tests/test_prompt_catalog.py`:

```python
from app.agents.shared.prompt_catalog import list_prompt_lifecycle_workflows


def test_prompt_lifecycle_workflows_expose_six_story_lanes() -> None:
    workflows = list_prompt_lifecycle_workflows()
    keys = [workflow["key"] for workflow in workflows]

    assert keys == [
        "story_foundation_lifecycle",
        "book_structure_lifecycle",
        "volume_rolling_lifecycle",
        "chapter_closed_loop_lifecycle",
        "serial_maintenance_lifecycle",
        "special_booster_lifecycle",
    ]
    assert all(workflow["workflow_kind"] == "prompt_lifecycle" for workflow in workflows)


def test_chapter_closed_loop_keeps_shortcuts_out_of_formal_chain() -> None:
    workflow = next(
        item for item in list_prompt_lifecycle_workflows()
        if item["key"] == "chapter_closed_loop_lifecycle"
    )
    node_ids = [node["id"] for node in workflow["nodes"]]

    assert node_ids == [
        "next_chapter_state_change",
        "chapter_card",
        "scene_outline",
        "draft_generation",
        "draft_self_check",
        "draft_rewrite",
        "narrative_ledger_update",
    ]
    assert "minimal_work_template" not in node_ids
    assert "single_round_generation_combo" not in node_ids

    edge_labels = {edge["label"] for edge in workflow["edges"]}
    assert {"passed", "needs_revision / blocked", "更新叙事账本"}.issubset(edge_labels)


def test_special_booster_contains_shortcut_prompt_agents() -> None:
    workflow = next(
        item for item in list_prompt_lifecycle_workflows()
        if item["key"] == "special_booster_lifecycle"
    )
    node_ids = {node["id"] for node in workflow["nodes"]}

    assert {"minimal_work_template", "single_round_generation_combo"}.issubset(node_ids)
    shortcut_nodes = [node for node in workflow["nodes"] if node["id"] in {"minimal_work_template", "single_round_generation_combo"}]
    assert all(node["node_subtype"] == "prompt_agent" for node in shortcut_nodes)
    assert all("shortcut" in node["tags"] for node in shortcut_nodes)


def test_lifecycle_prompt_nodes_reuse_prompt_agent_schemas() -> None:
    workflows = list_prompt_lifecycle_workflows()
    prompt_nodes = [
        node
        for workflow in workflows
        for node in workflow["nodes"]
        if node["type"] == "prompt"
    ]

    assert prompt_nodes
    assert all(node["node_subtype"] == "prompt_agent" for node in prompt_nodes)
    assert all(node["input_schema"]["type"] == "object" for node in prompt_nodes)
    assert all(node["output_schema"]["type"] == "object" for node in prompt_nodes)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest backend/tests/test_prompt_catalog.py -q
```

Expected: FAIL during import with `ImportError: cannot import name 'list_prompt_lifecycle_workflows'`.

- [ ] **Step 3: Implement lifecycle definitions**

In `backend/app/agents/shared/prompt_catalog.py`, add the dataclass after `PromptWorkflowDefinition`:

```python
@dataclass(frozen=True)
class PromptLifecycleWorkflowDefinition:
    key: str
    label: str
    description: str
    prompt_ids: tuple[str, ...]
    edges: tuple[dict[str, str], ...]
    trigger_policy: str = "manual"
    tags: tuple[str, ...] = ()
```

Add lifecycle workflow definitions after `PROMPT_WORKFLOWS`:

```python
PROMPT_LIFECYCLE_WORKFLOWS: tuple[PromptLifecycleWorkflowDefinition, ...] = (
    PromptLifecycleWorkflowDefinition(
        key="story_foundation_lifecycle",
        label="立项与宪法",
        description="从创作 Star 已确认种子生成核心矛盾、小说宪法、压力测试和正典候选。",
        prompt_ids=("core_conflict_system", "novel_constitution", "constitution_stress_test"),
        edges=(
            {"source": "core_conflict_system", "target": "novel_constitution", "label": "生成小说宪法"},
            {"source": "novel_constitution", "target": "constitution_stress_test", "label": "压力测试"},
            {"source": "constitution_stress_test", "target": "core_conflict_system", "label": "needs_revision / blocked"},
        ),
        tags=("foundation", "quality_gate"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="book_structure_lifecycle",
        label="全书结构推演",
        description="从小说宪法推演宏观大纲、结局反推、反派、高潮和结构审查。",
        prompt_ids=("macro_outline", "ending_backcast", "antagonist_design", "climax_design", "structure_editor_review"),
        edges=(
            {"source": "macro_outline", "target": "ending_backcast", "label": "反推结局路径"},
            {"source": "ending_backcast", "target": "antagonist_design", "label": "设计对立压力"},
            {"source": "antagonist_design", "target": "climax_design", "label": "压缩高潮候选"},
            {"source": "climax_design", "target": "structure_editor_review", "label": "结构审查"},
            {"source": "structure_editor_review", "target": "macro_outline", "label": "needs_revision / blocked"},
        ),
        tags=("book_structure", "quality_gate"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="volume_rolling_lifecycle",
        label="分卷与滚动章纲",
        description="将全书结构落到当前卷，并维护滚动章纲、上下文压缩和后续修正。",
        prompt_ids=("volume_outline", "rolling_chapter_outline", "context_compression", "rolling_outline_revision"),
        edges=(
            {"source": "volume_outline", "target": "rolling_chapter_outline", "label": "生成滚动章纲"},
            {"source": "rolling_chapter_outline", "target": "context_compression", "label": "压缩上下文"},
            {"source": "context_compression", "target": "rolling_outline_revision", "label": "体检后修正"},
            {"source": "rolling_outline_revision", "target": "rolling_chapter_outline", "label": "revision_loop"},
        ),
        trigger_policy="on_volume_or_outline_window",
        tags=("rolling", "revision_loop"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="chapter_closed_loop_lifecycle",
        label="单章生产闭环",
        description="从下一章状态变化到章节卡、场景细纲、正文、自检、改写和叙事账本更新。",
        prompt_ids=(
            "next_chapter_state_change",
            "chapter_card",
            "scene_outline",
            "draft_generation",
            "draft_self_check",
            "draft_rewrite",
            "narrative_ledger_update",
        ),
        edges=(
            {"source": "next_chapter_state_change", "target": "chapter_card", "label": "确定本章改变什么"},
            {"source": "chapter_card", "target": "scene_outline", "label": "拆成场景细纲"},
            {"source": "scene_outline", "target": "draft_generation", "label": "生成正文"},
            {"source": "draft_generation", "target": "draft_self_check", "label": "正文自检"},
            {"source": "draft_self_check", "target": "draft_rewrite", "label": "needs_revision / blocked"},
            {"source": "draft_self_check", "target": "narrative_ledger_update", "label": "passed"},
            {"source": "draft_rewrite", "target": "narrative_ledger_update", "label": "更新叙事账本"},
        ),
        trigger_policy="on_chapter_generation",
        tags=("chapter", "quality_gate", "revision_loop"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="serial_maintenance_lifecycle",
        label="连载维护与体检",
        description="并行检查伏笔、人物、关系、世界规则、时间线、风格，并汇总结构体检结果。",
        prompt_ids=(
            "foreshadowing_management",
            "character_arc_management",
            "relationship_network_management",
            "world_rules_management",
            "timeline_check",
            "style_calibration",
            "structure_editor_review",
            "ten_chapter_health_check",
            "rolling_outline_revision",
        ),
        edges=(
            {"source": "foreshadowing_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "character_arc_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "relationship_network_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "world_rules_management", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "timeline_check", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "style_calibration", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "structure_editor_review", "target": "rolling_outline_revision", "label": "revise_outline"},
            {"source": "ten_chapter_health_check", "target": "rolling_outline_revision", "label": "revise_outline"},
        ),
        trigger_policy="every_10_chapters_or_manual",
        tags=("maintenance", "parallel_check"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="special_booster_lifecycle",
        label="专项增强",
        description="按需调用分支、支线、反派、高潮、工作流推荐和快捷写作模式。",
        prompt_ids=(
            "branch_plot_generation",
            "subplot_design",
            "antagonist_design",
            "climax_design",
            "recommended_workflow_order",
            "minimal_work_template",
            "single_round_generation_combo",
        ),
        edges=(
            {"source": "branch_plot_generation", "target": "subplot_design", "label": "扩展支线"},
            {"source": "subplot_design", "target": "antagonist_design", "label": "强化对立压力"},
            {"source": "antagonist_design", "target": "climax_design", "label": "强化高潮"},
            {"source": "recommended_workflow_order", "target": "minimal_work_template", "label": "shortcut"},
            {"source": "minimal_work_template", "target": "single_round_generation_combo", "label": "shortcut"},
        ),
        trigger_policy="manual",
        tags=("booster", "shortcut"),
    ),
)
```

Add these functions near `list_prompt_workflows()`:

```python
def list_prompt_lifecycle_workflows() -> list[dict[str, object]]:
    workflows: list[dict[str, object]] = []
    for workflow in PROMPT_LIFECYCLE_WORKFLOWS:
        entries = [get_prompt_entry(prompt_id) for prompt_id in workflow.prompt_ids]
        agents = list(dict.fromkeys(entry.default_agent for entry in entries))
        workflows.append(
            {
                "id": workflow.key,
                "key": workflow.key,
                "label": workflow.label,
                "description": workflow.description,
                "workflow_kind": "prompt_lifecycle",
                "trigger_policy": workflow.trigger_policy,
                "tags": list(workflow.tags),
                "prompt_ids": list(workflow.prompt_ids),
                "prompts": [_prompt_summary(entry) for entry in entries],
                "agents": agents,
                "nodes": [
                    _prompt_workflow_node(
                        entry,
                        position,
                        workflow_tags=workflow.tags,
                    )
                    for position, entry in enumerate(entries)
                ],
                "edges": [dict(edge) for edge in workflow.edges],
            }
        )
    return workflows


def _prompt_summary(entry: PromptCatalogEntry) -> dict[str, object]:
    return {
        "id": entry.prompt_id,
        "index": entry.index,
        "title": entry.title,
        "filename": entry.filename,
        "default_agent": entry.default_agent,
    }
```

Change `_prompt_workflow_node()` signature and body:

```python
def _prompt_workflow_node(
    entry: PromptCatalogEntry,
    position: int,
    workflow_tags: tuple[str, ...] = (),
) -> dict[str, object]:
    contract = get_prompt_node_contract(entry.prompt_id)
    node_tags = list(workflow_tags)
    if entry.prompt_id in {"minimal_work_template", "single_round_generation_combo"}:
        node_tags.append("shortcut")
    return {
        "id": entry.prompt_id,
        "label": entry.title,
        "type": "prompt",
        "node_subtype": contract.node_subtype,
        "agent_name": entry.default_agent,
        "description": contract.description,
        "inputs": list(contract.required_inputs),
        "outputs": list(contract.produces),
        "required_inputs": list(contract.required_inputs),
        "optional_inputs": list(contract.optional_inputs),
        "produces": list(contract.produces),
        "input_schema": contract.input_json_schema(),
        "output_schema": contract.output_json_schema(),
        "editable": True,
        "layer": position + 1,
        "prompt_id": entry.prompt_id,
        "prompt_filename": entry.filename,
        "tags": node_tags,
    }
```

In `list_prompt_workflows()`, replace inline prompt summaries with `_prompt_summary(entry)` and add:

```python
"workflow_kind": "prompt_library",
"trigger_policy": "manual",
"tags": ["prompt_library"],
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest backend/tests/test_prompt_catalog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/shared/prompt_catalog.py backend/tests/test_prompt_catalog.py
git commit -m "feat: add prompt lifecycle workflow catalog"
```

---

### Task 2: Expose Lifecycle Workflows Through Studio Service

**Files:**
- Modify: `backend/app/services/studio_service.py`
- Modify: `backend/tests/test_agent_prompt_runtime_contract.py`

- [ ] **Step 1: Write failing API tests**

Append this test to `backend/tests/test_agent_prompt_runtime_contract.py`:

```python
def test_workflows_api_exposes_prompt_lifecycle_views_and_keeps_legacy_prompt_lanes() -> None:
    reset_database()
    client = TestClient(app)

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    by_key = {workflow["key"]: workflow for workflow in workflows}

    assert "chapter_closed_loop_lifecycle" in by_key
    assert "special_booster_lifecycle" in by_key
    assert "chapter_production" in by_key

    lifecycle = by_key["chapter_closed_loop_lifecycle"]
    assert lifecycle["workflow_kind"] == "prompt_lifecycle"
    assert lifecycle["runtime_status"] == "applied_via_prompt_binding"
    assert lifecycle["trigger_policy"] == "on_chapter_generation"

    node_ids = [node["id"] for node in lifecycle["nodes"]]
    assert node_ids[:4] == ["next_chapter_state_change", "chapter_card", "scene_outline", "draft_generation"]
    assert "minimal_work_template" not in node_ids
    assert all(node["node_subtype"] == "prompt_agent" for node in lifecycle["nodes"] if node["type"] == "prompt")

    legacy = by_key["chapter_production"]
    assert legacy["workflow_kind"] == "prompt_library"
    assert legacy["runtime_status"] == "applied_via_prompt_binding"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest backend/tests/test_agent_prompt_runtime_contract.py::test_workflows_api_exposes_prompt_lifecycle_views_and_keeps_legacy_prompt_lanes -q
```

Expected: FAIL because `chapter_closed_loop_lifecycle` is absent from `/api/workflows`.

- [ ] **Step 3: Wire lifecycle workflows into `StudioService.list_workflows()`**

In `backend/app/services/studio_service.py`, update the import:

```python
from app.agents.shared.prompt_catalog import get_prompt_entry, list_prompt_lifecycle_workflows, list_prompt_workflows
```

In `StudioService.list_workflows()`, after the existing runtime workflows are added and before or near legacy prompt workflows, add lifecycle workflows first:

```python
        workflows.extend(
            [
                self._apply_agent_model_configs_to_workflow(self._with_workflow_runtime_metadata(workflow), model_configs)
                for workflow in list_prompt_lifecycle_workflows()
            ]
        )
        workflows.extend(
            [
                self._apply_agent_model_configs_to_workflow(self._with_workflow_runtime_metadata(workflow), model_configs)
                for workflow in list_prompt_workflows()
            ]
        )
```

If `list_prompt_workflows()` is already extended there, replace that single block with the two blocks above.

- [ ] **Step 4: Run API test to verify GREEN**

Run:

```bash
python -m pytest backend/tests/test_agent_prompt_runtime_contract.py::test_workflows_api_exposes_prompt_lifecycle_views_and_keeps_legacy_prompt_lanes -q
```

Expected: PASS.

- [ ] **Step 5: Run focused backend regression**

Run:

```bash
python -m pytest backend/tests/test_prompt_catalog.py backend/tests/test_agent_prompt_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/studio_service.py backend/tests/test_agent_prompt_runtime_contract.py
git commit -m "feat: expose prompt lifecycle workflows"
```

---

### Task 3: Frontend Types And Agent Menu Defaults

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/AgentsPage.tsx`
- Modify: `frontend/tests/agents-page-contract.test.mjs`

- [ ] **Step 1: Write failing frontend contract test**

Append this test to `frontend/tests/agents-page-contract.test.mjs`:

```javascript
test("agents page defaults to lifecycle workflows and keeps prompt library visible", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const types = read("src/types/api.ts");

  assert.match(types, /workflow_kind\?: "runtime" \| "prompt_lifecycle" \| "prompt_library" \| string/);
  assert.match(types, /trigger_policy\?: string/);
  assert.match(types, /tags\?: string\[\]/);
  assert.match(page, /chapter_closed_loop_lifecycle/);
  assert.match(page, /workflowKindLabel/);
  assert.match(page, /prompt_lifecycle/);
  assert.match(page, /prompt_library/);
  assert.match(page, /工作流视图/);
  assert.match(page, /提示词库视图/);
});
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
pnpm --dir frontend test -- agents-page-contract.test.mjs
```

Expected: FAIL on missing `workflow_kind` and `workflowKindLabel`.

- [ ] **Step 3: Extend frontend API types**

In `frontend/src/types/api.ts`, extend `WorkflowNode` and `WorkflowDefinition`:

```typescript
export interface WorkflowNode {
  id: string;
  label: string;
  type: "agent" | "control" | "prompt";
  node_subtype?: string;
  agent_name: string | null;
  description: string;
  inputs: string[];
  outputs: string[];
  required_inputs?: string[];
  optional_inputs?: string[];
  produces?: string[];
  input_schema?: WorkflowNodeSchema;
  output_schema?: WorkflowNodeSchema;
  editable: boolean;
  layer: number;
  prompt_id?: string;
  prompt_filename?: string;
  provider?: string | null;
  model?: string | null;
  model_config_id?: string | null;
  tags?: string[];
}

export interface WorkflowDefinition {
  id: string;
  key?: string;
  label: string;
  workflow_kind?: "runtime" | "prompt_lifecycle" | "prompt_library" | string;
  trigger_policy?: string;
  tags?: string[];
  runtime_status: "active_runtime" | "applied_via_prompt_binding";
  runtime_note: string;
  entrypoints: string[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}
```

- [ ] **Step 4: Update `AgentsPage` workflow ordering and labels**

In `frontend/src/pages/AgentsPage.tsx`, change initial state:

```typescript
const [workflowId, setWorkflowId] = useState("chapter_closed_loop_lifecycle");
```

Add helper functions near `workflowRuntimeLabel()`:

```typescript
function workflowKindRank(workflow: WorkflowDefinition) {
  if (workflow.workflow_kind === "prompt_lifecycle") return 0;
  if (workflow.runtime_status === "active_runtime") return 1;
  if (workflow.workflow_kind === "prompt_library") return 2;
  return 3;
}

function workflowKindLabel(workflow: WorkflowDefinition) {
  if (workflow.workflow_kind === "prompt_lifecycle") return "工作流视图";
  if (workflow.workflow_kind === "prompt_library") return "提示词库视图";
  return workflow.runtime_status === "active_runtime" ? "运行工作流" : "工作流";
}

function workflowKindColor(workflow: WorkflowDefinition) {
  if (workflow.workflow_kind === "prompt_lifecycle") return "green";
  if (workflow.workflow_kind === "prompt_library") return "purple";
  return workflow.runtime_status === "active_runtime" ? "blue" : "default";
}
```

Change workflow list creation:

```typescript
const workflows = useMemo(() => {
  return [...(workflowsQuery.data?.workflows ?? [])].sort((left, right) => {
    const rankDelta = workflowKindRank(left) - workflowKindRank(right);
    if (rankDelta !== 0) return rankDelta;
    return left.label.localeCompare(right.label, "zh-CN");
  });
}, [workflowsQuery.data?.workflows]);
```

Change workflow selector options:

```typescript
options={workflows.map((workflow) => ({
  value: workflow.id,
  label: `${workflowKindLabel(workflow)} · ${workflow.label}`,
}))}
```

In the runtime `Alert` message `Space`, add:

```tsx
<Tag color={workflowKindColor(activeWorkflow)}>{workflowKindLabel(activeWorkflow)}</Tag>
```

In the node list button, after the subtype tag, add:

```tsx
{node.tags?.includes("shortcut") ? <Tag color="gold">shortcut</Tag> : null}
```

- [ ] **Step 5: Run frontend contract test to verify GREEN**

Run:

```bash
pnpm --dir frontend test -- agents-page-contract.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/pages/AgentsPage.tsx frontend/tests/agents-page-contract.test.mjs
git commit -m "feat: default agents page to lifecycle workflows"
```

---

### Task 4: Backend And Frontend Regression Verification

**Files:**
- No new implementation files.
- Verify changes from Tasks 1-3.

- [ ] **Step 1: Run full backend tests**

Run:

```bash
python -m pytest backend/tests -q
```

Expected: `83 passed` or more, depending on newly added tests. One existing `StarletteDeprecationWarning` is acceptable.

- [ ] **Step 2: Run frontend contract tests**

Run:

```bash
pnpm --dir frontend test -- agents-page-contract.test.mjs
```

Expected: all frontend contract tests pass. Existing Node engine warning is acceptable if the machine still runs Node v26 instead of the project-pinned Node 24.14.0.

- [ ] **Step 3: Run frontend build**

Run:

```bash
pnpm --dir frontend build
```

Expected: TypeScript and Vite build pass. Existing chunk-size warning is acceptable.

- [ ] **Step 4: Inspect `/api/workflows` payload shape manually**

Run:

```bash
python - <<'PY'
from app.services.studio_service import studio_service

workflows = studio_service.list_workflows()["workflows"]
for key in [
    "chapter_closed_loop_lifecycle",
    "special_booster_lifecycle",
    "chapter_production",
]:
    workflow = next(item for item in workflows if item["key"] == key)
    print(key, workflow.get("workflow_kind"), [node["id"] for node in workflow["nodes"][:4]])
PY
```

Expected output includes:

```text
chapter_closed_loop_lifecycle prompt_lifecycle ['next_chapter_state_change', 'chapter_card', 'scene_outline', 'draft_generation']
special_booster_lifecycle prompt_lifecycle ['branch_plot_generation', 'subplot_design', 'antagonist_design', 'climax_design']
chapter_production prompt_library ['chapter_card', 'scene_outline', 'draft_generation', 'draft_self_check']
```

- [ ] **Step 5: Commit verification-only doc note if any command requires documented caveat**

If verification reveals only known warnings, do not create a commit. If a new warning or caveat needs documentation, update the relevant README/AGENTS section and commit only that documentation change:

```bash
git add README.md AGENTS.md
git commit -m "docs: note lifecycle workflow verification caveat"
```

---

## Self-Review Checklist

- [ ] Spec coverage: six lifecycle workflows are implemented, old prompt-library lanes are preserved, shortcut nodes are separated from formal chapter workflow, and quality-gate edges are visible.
- [ ] Placeholder scan: the plan contains no unfinished-marker text and no unspecified implementation steps.
- [ ] Type consistency: backend uses `workflow_kind`, `trigger_policy`, `tags`; frontend uses the same names.
- [ ] Test consistency: backend tests assert catalog and API behavior; frontend tests assert UI/type behavior.
- [ ] Boundary consistency: no 32 new formal Agents are introduced; every prompt node remains `node_subtype="prompt_agent"`.
