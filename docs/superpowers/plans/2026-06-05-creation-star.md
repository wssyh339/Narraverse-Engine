# Creation Star Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full-stack creation-card wizard in the workspace.

**Architecture:** Backend exposes deterministic, LLM-ready card drawing APIs and a confirmed commit API. Frontend renders a multi-step Ant Design drawer and only writes confirmed results into project canon.

**Tech Stack:** FastAPI, pydantic v2, SQLAlchemy, React, TypeScript, Ant Design, existing Axios client.

---

### Task 1: Backend Contract

**Files:**
- Modify: `backend/app/agents/prompts.py`
- Modify: `backend/app/schemas/studio.py`
- Modify: `backend/app/services/studio_service.py`
- Modify: `backend/app/api/v1/endpoints/studio.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_creation_star.py`

- [ ] Add failing API tests for options, worldview draw, protagonist draw, bible draw, and commit.
- [ ] Add `creation_star` default Agent prompt.
- [ ] Add pydantic schemas for draw and commit.
- [ ] Add service methods that produce structured fallback cards and persist confirmed choices.
- [ ] Register routes and verify unified response envelopes.

### Task 2: Frontend Contract

**Files:**
- Modify: `frontend/src/api/studio.ts`
- Create: `frontend/src/components/CreationStarWizard.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/frontend-contract.test.mjs`

- [ ] Add failing frontend contract assertions for the first toolbar button, API methods, and wizard step names.
- [ ] Add typed API methods.
- [ ] Build the wizard using Ant Design Drawer, Steps, Cards, Form, Select, Tag, and editable text areas.
- [ ] Invalidate project state after commit.

### Task 3: Verification

**Files:**
- Existing tests and build scripts.

- [ ] Run backend pytest.
- [ ] Run frontend test.
- [ ] Run frontend production build.

