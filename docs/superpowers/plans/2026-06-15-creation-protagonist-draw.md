# Creation Protagonist Draw Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split 创作 Star 主角人设抽卡 into a dedicated prompt and faster execution path that only generates protagonist candidate cards.

**Architecture:** Add `creation_protagonist_draw` to the local prompt catalog, but keep the public 11-agent role model unchanged. Route only the protagonist draw step to this prompt, normalize new fields for backwards compatibility, and leave core conflict / novel constitution generation in the later `chief_architect` stage.

**Tech Stack:** FastAPI service layer, local Markdown prompt catalog, Pydantic prompt node contracts, React + TypeScript frontend display, pytest, pnpm build.

---

### Task 1: Lock Dedicated Protagonist Prompt Contract

**Files:**
- Modify: `backend/tests/test_prompt_catalog.py`
- Create: `backend/app/prompts/33_creation_protagonist_draw_prompt.md`
- Modify: `backend/app/agents/shared/prompt_catalog.py`
- Modify: `backend/app/schemas/prompt_nodes.py`
- Modify: `backend/app/agents/shared/prompt_node_contracts.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting `creation_protagonist_draw` is registered, loads prompt text, forbids core conflict / constitution generation, and exposes a prompt-agent node contract.

- [ ] **Step 2: Run targeted tests and verify RED**

Run:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_prompt_catalog.py -q
```

Expected: fails because `creation_protagonist_draw` does not exist.

- [ ] **Step 3: Implement catalog, prompt file, and contract**

Add the Markdown prompt and register it as `PromptCatalogEntry(... index=33, workflow="creation_star", default_agent="creation_star")`.

- [ ] **Step 4: Verify GREEN**

Run the same pytest command and expect pass.

### Task 2: Route Protagonist Draw To Dedicated Prompt

**Files:**
- Modify: `backend/tests/test_creation_star.py`
- Modify: `backend/app/services/studio_service.py`
- Modify: `backend/app/agents/creation_star/service.py`

- [ ] **Step 1: Write failing tests**

Add tests for both session `/protagonists` and legacy `/creation-star/draw` with `step=protagonist`, asserting calls use `agent_name=creation_protagonist_draw`, prompt snapshot has `prompt_id=creation_protagonist_draw`, and returned cards include `world_rule_connection`, `conflict_seed`, `ability_cost`.

- [ ] **Step 2: Run targeted tests and verify RED**

Run:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_creation_star.py::test_creation_star_protagonist_draw_calls_dedicated_llm_client backend/tests/test_creation_star.py::test_creation_session_protagonist_uses_dedicated_prompt -q
```

Expected: fails because protagonist still routes through `creation_star`.

- [ ] **Step 3: Implement service helpers**

Add `_creation_protagonist_agent_name`, `_creation_protagonist_system_prompt`, `_creation_protagonist_runtime_strategy`, `_creation_protagonist_output_schema`, and `_normalize_creation_protagonist_cards`.

- [ ] **Step 4: Update routing**

In `_run_creation_star_draw_step` and legacy `CreationStarAgentService.draw`, route `step == "protagonist"` to `creation_protagonist_draw`.

- [ ] **Step 5: Verify GREEN**

Run targeted tests and then full backend tests.

### Task 3: Frontend Display And Real Speed Comparison

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/components/CreationStarWizard.tsx`

- [ ] **Step 1: Add frontend fields**

Expose protagonist card fields: `one_sentence_pitch`, `opening_situation`, `world_rule_connection`, `ability_cost`, `relationship_hooks`, `conflict_seed`, `reader_satisfaction`, `long_form_potential`, `writing_risk`.

- [ ] **Step 2: Build frontend**

Run:

```bash
pnpm -C frontend build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 3: Compare real API speed**

Use `llm_client.generate` with old total creation-star prompt versus `creation_protagonist_draw`, same model and one-card output. Select the faster path; expected winner is dedicated prompt due shorter prompt and narrower schema.
