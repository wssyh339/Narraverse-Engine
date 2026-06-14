# Agents Prompt Workflow Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 32 long-novel prompt markdown files into a typed prompt catalog and workflow map that agents can consume without breaking existing API contracts.

**Architecture:** Add a small prompt catalog module under `backend/app/agents/shared/` that maps prompt ids to files, stages, workflow lanes, and default agent ownership. Keep existing agent names and routes stable, then expose the five high-level workflows through `StudioService.list_workflows()`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, existing markdown prompt files under `backend/app/prompts`.

---

### Task 1: Prompt Catalog

**Files:**
- Create: `backend/app/agents/shared/prompt_catalog.py`
- Test: `backend/tests/test_prompt_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
from app.agents.shared.prompt_catalog import (
    LONG_NOVEL_PROMPT_IDS,
    get_prompt_entry,
    list_long_novel_prompt_entries,
    load_catalog_prompt,
)


def test_long_novel_catalog_covers_all_32_prompt_files() -> None:
    entries = list_long_novel_prompt_entries()
    assert len(entries) == 32
    assert LONG_NOVEL_PROMPT_IDS[0] == "general_control"
    assert LONG_NOVEL_PROMPT_IDS[-1] == "single_round_generation_combo"
    assert entries[0].filename == "00_general_control_prompt.md"
    assert entries[-1].filename == "31_single_round_generation_combo_prompt.md"


def test_catalog_loads_prompt_text_and_metadata() -> None:
    entry = get_prompt_entry("chapter_card")
    assert entry.index == 8
    assert entry.workflow == "chapter_production"
    assert entry.default_agent == "chapter_planner"
    text = load_catalog_prompt("chapter_card")
    assert text.startswith("# 8. 单章章节卡生成提示词")
    assert "章节功能" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompt_catalog.py -q`

Expected: FAIL with missing `app.agents.shared.prompt_catalog`.

- [ ] **Step 3: Implement catalog**

Create frozen dataclasses and dictionaries for the 32 prompt files, grouped into five workflow names: `conception`, `outline_planning`, `chapter_production`, `serial_maintenance`, `special_design`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prompt_catalog.py -q`

Expected: PASS.

### Task 2: Agent Prompt Binding

**Files:**
- Modify: `backend/app/agents/prompts.py`
- Test: `backend/tests/test_prompt_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
from app.agents.prompts import AGENT_PROMPT_BINDINGS


def test_agent_bindings_route_new_prompt_library_to_existing_agents() -> None:
    assert "novel_constitution" in AGENT_PROMPT_BINDINGS["chief_architect"]
    assert "chapter_card" in AGENT_PROMPT_BINDINGS["chapter_planner"]
    assert "scene_outline" in AGENT_PROMPT_BINDINGS["plot_narrator"]
    assert "draft_self_check" in AGENT_PROMPT_BINDINGS["reviewer"]
    assert "narrative_ledger_update" in AGENT_PROMPT_BINDINGS["canon_curator"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompt_catalog.py::test_agent_bindings_route_new_prompt_library_to_existing_agents -q`

Expected: FAIL with missing `AGENT_PROMPT_BINDINGS`.

- [ ] **Step 3: Add bindings**

Add `AGENT_PROMPT_BINDINGS` and append concise loaded prompt excerpts to default `AgentSpec.prompt` text through a helper so existing `AgentSpec` and `/api/agents` remain compatible.

- [ ] **Step 4: Run prompt tests**

Run: `cd backend && pytest tests/test_prompt_catalog.py -q`

Expected: PASS.

### Task 3: Workflow Exposure

**Files:**
- Modify: `backend/app/services/studio_service.py`
- Test: `backend/tests/test_prompt_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
from app.services.studio_service import studio_service


def test_studio_workflows_expose_five_long_novel_lanes() -> None:
    workflows = studio_service.list_workflows()["workflows"]
    keys = {item["key"] for item in workflows}
    assert {
        "conception",
        "outline_planning",
        "chapter_production",
        "serial_maintenance",
        "special_design",
    }.issubset(keys)
    chapter = next(item for item in workflows if item["key"] == "chapter_production")
    assert chapter["prompt_ids"][:3] == ["chapter_card", "scene_outline", "draft_generation"]
    assert chapter["agents"][:2] == ["chapter_planner", "plot_narrator"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompt_catalog.py::test_studio_workflows_expose_five_long_novel_lanes -q`

Expected: FAIL because existing workflows do not expose the new prompt ids.

- [ ] **Step 3: Update workflow listing**

Extend `StudioService.list_workflows()` to include catalog-derived workflow entries while preserving existing workflow data expected by current tests.

- [ ] **Step 4: Run focused tests**

Run: `cd backend && pytest tests/test_prompt_catalog.py tests/test_core_apis.py::test_plan_chapters_creates_job_and_chapter_placeholders -q`

Expected: PASS.

### Task 4: Explicit Chapter Production State

**Files:**
- Modify: `backend/app/agents/contracts.py`
- Modify: `backend/app/agents/chapter_writing/workflow.py`
- Modify: `backend/app/services/studio_service.py`
- Test: `backend/tests/test_core_apis.py`

- [x] **Step 1: Write failing tests**

Add assertions that `run_chapter_draft()` returns `chapter_card`, `scene_outline`, and `narrative_ledger`, and that the API draft endpoint records the expanded node sequence.

- [x] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_core_apis.py::test_draft_workflow_builds_context_quality_gate_and_candidate_canon_updates backend/tests/test_core_apis.py::test_core_agent_workflows_call_llm_client_for_agent_nodes -q`

Observed: FAIL with `NovelStudioState` missing `chapter_card`.

- [x] **Step 3: Add state fields and nodes**

Add state fields for prompt-driven artifacts, then insert `chapter_card`, `scene_outline`, `draft_rewrite`, and `narrative_ledger` nodes into the chapter LangGraph flow.

- [x] **Step 4: Record expanded job trace**

Update `draft_chapter()` to use 14 total steps and persist Agent runs for `chapter_card`, `scene_outline`, `draft_rewrite`, and `narrative_ledger`.

- [x] **Step 5: Run focused tests**

Run: `pytest backend/tests/test_core_apis.py::test_draft_workflow_builds_context_quality_gate_and_candidate_canon_updates backend/tests/test_core_apis.py::test_core_agent_workflows_call_llm_client_for_agent_nodes backend/tests/test_core_apis.py::test_1_0_draft_graph_versions_and_export_flow -q`

Expected: PASS.

### Task 5: Explicit Conception And Outline State

**Files:**
- Modify: `backend/app/agents/contracts.py`
- Modify: `backend/app/agents/chapter_writing/workflow.py`
- Modify: `backend/app/services/studio_service.py`
- Test: `backend/tests/test_core_apis.py`

- [x] **Step 1: Write failing tests**

Extend the LLM wiring contract to require `run_initialization()` to produce `novel_constitution` and `constitution_review`, and `run_chapter_plan()` to produce `macro_outline`, `ending_backcast`, `volume_outline`, and `rolling_chapter_outline`.

- [x] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_core_apis.py::test_core_agent_workflows_call_llm_client_for_agent_nodes -q`

Observed: FAIL because `novel_constitution` did not mirror the generated story bible.

- [x] **Step 3: Add conception and outline artifacts**

Add `core_conflict_system`, `novel_constitution`, `constitution_review`, `macro_outline`, `ending_backcast`, `volume_outline`, and `rolling_chapter_outline` state handling.

- [x] **Step 4: Expose initialization artifacts through API result**

Update `generate_story_bible()` to include the new conception artifacts in agent runs and job results.

- [x] **Step 5: Run focused and full tests**

Run: `pytest backend/tests/test_core_apis.py::test_draft_workflow_builds_context_quality_gate_and_candidate_canon_updates backend/tests/test_core_apis.py::test_core_agent_workflows_call_llm_client_for_agent_nodes backend/tests/test_core_apis.py::test_1_0_draft_graph_versions_and_export_flow -q`

Run: `pytest backend/tests -q`

Expected: PASS.
