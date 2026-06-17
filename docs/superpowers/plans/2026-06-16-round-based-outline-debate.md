# Round-Based Outline Debate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn outline debate from full-run SSE replay into a round-based discussion flow where the user can join, @ an agent, interrupt, continue, or ask for a phase conclusion.

**Architecture:** Keep `outline_debate` as a service backed by `generation_jobs.result_json`. Existing `/stream` endpoints remain compatible: automatic mode completes a phase, while `join_discussion=true` advances one turn and emits `pause`. User controls are separate POST actions that update session state and influence the next streamed turn.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, existing unified LLM client, React 18, TypeScript, Ant Design, assistant-ui shell, SSE fetch reader.

---

### Task 1: Contract Tests

**Files:**
- Modify: `backend/tests/test_outline_debate_engine.py`
- Modify: `frontend/tests/frontend-contract.test.mjs`

- [ ] Add backend tests for one-turn pause, user message mention routing, interrupt status, and finish-phase summary.
- [ ] Add frontend contract expectations for `Mentions`, “加入讨论”, “发表意见”, “继续下一轮”, “打断发言”, “形成阶段结论”, `postOutlineDebateMessage`, and `interruptOutlineDebateSession`.
- [ ] Run `pytest backend/tests/test_outline_debate_engine.py -q` and confirm the new tests fail before production changes.
- [ ] Run `cd frontend && pnpm test -- tests/frontend-contract.test.mjs` and confirm the new contract checks fail before production changes.

### Task 2: Backend Round State

**Files:**
- Modify: `backend/app/schemas/outline.py`
- Modify: `backend/app/services/outline_debate_service.py`
- Modify: `backend/app/api/v1/endpoints/outline_debate.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] Add request fields for `join_discussion`, `target_agent_name`, `user_message`, and `finish_phase`.
- [ ] Add message and interrupt request schemas.
- [ ] Implement session helpers that create or load a per-phase run with `turns`, `user_messages`, `decisions`, `artifacts`, `status`, `next_agent_name`, and `outline_topology`.
- [ ] Make `stream_phase(join_discussion=true)` generate one Agent turn, save the paused state, and emit `pause`.
- [ ] Make mentions from saved user messages prioritize the next Agent turn.
- [ ] Make `finish_phase=true` summarize current turns into decisions/artifacts/done.
- [ ] Keep `run_phase` and non-joined streaming compatible with existing tests.

### Task 3: Frontend Controls

**Files:**
- Modify: `frontend/src/api/studio.ts`
- Modify: `frontend/src/pages/outline/OutlineDebatePanel.tsx`
- Modify: `frontend/src/styles/index.css`

- [ ] Extend TypeScript event and payload types for `pause`, `user_message`, and `interrupt`.
- [ ] Add API helpers for user messages and interrupt.
- [ ] Replace plain text input with Ant Design `Mentions` for @角色.
- [ ] Add “加入讨论” switch and control buttons.
- [ ] In joined mode, keep event history, stream one turn, show pause state, and let “继续下一轮” resume the same phase.
- [ ] Let “发表意见” save a user message without directly changing artifacts.
- [ ] Let “打断发言” abort the current stream and mark the session interrupted.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `pytest backend/tests/test_outline_debate_engine.py -q`.
- [ ] Run broader backend API checks if targeted tests pass: `pytest backend/tests/test_core_apis.py backend/tests/test_outline_agent_pipeline.py -q`.
- [ ] Run `cd frontend && pnpm test -- tests/frontend-contract.test.mjs`.
- [ ] Run `cd frontend && pnpm build`.
- [ ] If a local dev server can be started cleanly, use the in-app Browser flow to inspect the outline debate UI.
