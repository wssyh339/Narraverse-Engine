# Agents Three Lanes LangGraph Swarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `backend/app/agents` into Creation Star, Outline Swarm, and Chapter Writing lanes, then introduce a `langgraph_swarm` outline-generation skeleton with dynamic handoff, stop conditions, and no hardcoded story content.

**Architecture:** Keep existing API paths stable while moving implementation behind lane-specific services. Creation Star remains a guided candidate generator, Chapter Writing remains deterministic LangGraph StateGraph with a stronger quality loop, and Outline Generation becomes the only lane using `langgraph_swarm`. Legacy modules remain as wrappers until callers are migrated.

**Tech Stack:** Python 3.13-compatible code, pydantic v2, FastAPI service layer, LangGraph 1.2.4, `langgraph-swarm==0.1.0`, existing pytest suite.

---

## File Map

- Create `backend/app/agents/shared/`: common state helpers, prompt loader, trace helpers, and canon-context contracts.
- Create `backend/app/agents/creation_star/`: guided Star state, workflow facade, and service shell.
- Create `backend/app/agents/outline_swarm/`: pydantic state, no-hardcode prompts, tools, validators, and Swarm builder.
- Create `backend/app/agents/chapter_writing/`: wrapper around current chapter workflow and future quality-loop implementation.
- Modify `backend/requirements.txt` and root `requirements.txt`: add `langgraph-swarm`.
- Modify `AGENTS.md` and `README.md`: document three lanes and Swarm boundary.
- Add tests under `backend/tests/`: structure contract, dependency contract, no-hardcoded-story guard, state/validator tests, and Swarm fallback tests.

---

### Task 1: Structure And Dependency Contract

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `requirements.txt`
- Create: `backend/tests/test_agents_three_lanes_contract.py`
- Create directories/files under `backend/app/agents/{shared,creation_star,outline_swarm,chapter_writing}`

- [ ] **Step 1: Write failing structure test**

Create `backend/tests/test_agents_three_lanes_contract.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agents_are_split_into_three_lanes() -> None:
    expected = {
        "backend/app/agents/shared/__init__.py",
        "backend/app/agents/shared/contracts.py",
        "backend/app/agents/shared/prompt_loader.py",
        "backend/app/agents/shared/trace.py",
        "backend/app/agents/shared/canon_context.py",
        "backend/app/agents/creation_star/__init__.py",
        "backend/app/agents/creation_star/state.py",
        "backend/app/agents/creation_star/workflow.py",
        "backend/app/agents/creation_star/service.py",
        "backend/app/agents/outline_swarm/__init__.py",
        "backend/app/agents/outline_swarm/state.py",
        "backend/app/agents/outline_swarm/tools.py",
        "backend/app/agents/outline_swarm/validators.py",
        "backend/app/agents/outline_swarm/swarm.py",
        "backend/app/agents/outline_swarm/service.py",
        "backend/app/agents/chapter_writing/__init__.py",
        "backend/app/agents/chapter_writing/state.py",
        "backend/app/agents/chapter_writing/workflow.py",
        "backend/app/agents/chapter_writing/service.py",
    }
    missing = [path for path in sorted(expected) if not (ROOT / path).exists()]
    assert missing == []


def test_langgraph_swarm_dependency_is_declared() -> None:
    backend_requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "langgraph-swarm" in backend_requirements
    assert "langgraph-swarm" in root_requirements
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_three_lanes_contract.py -q
```

Expected: FAIL because new directories and dependency do not exist yet.

- [ ] **Step 3: Create minimal lane packages**

Create the files named in Step 1 with minimal importable content:

```python
"""Lane package placeholder for staged agents refactor."""
```

For `backend/app/agents/shared/contracts.py`:

```python
from __future__ import annotations

from app.schemas.common import APIModel


class AgentLaneResult(APIModel):
    lane: str
    status: str
```

- [ ] **Step 4: Add dependency**

Append to both `backend/requirements.txt` and root `requirements.txt`:

```text
langgraph-swarm
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_three_lanes_contract.py -q
```

Expected: PASS.

---

### Task 2: Shared Contracts And Trace Utilities

**Files:**
- Modify: `backend/app/agents/shared/contracts.py`
- Create: `backend/app/agents/shared/trace.py`
- Create: `backend/app/agents/shared/canon_context.py`
- Test: `backend/tests/test_agents_shared_contracts.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_agents_shared_contracts.py`:

```python
from __future__ import annotations

from app.agents.shared.canon_context import CanonContext
from app.agents.shared.trace import AgentTraceEvent, append_trace


def test_canon_context_defaults_are_safe() -> None:
    context = CanonContext(project_id="prj_test")
    assert context.project_id == "prj_test"
    assert context.characters == []
    assert context.world_facts == []
    assert context.story_entities == []
    assert context.previous_summaries == []


def test_append_trace_adds_agent_event() -> None:
    events: list[AgentTraceEvent] = []
    append_trace(events, agent_name="StoryDirectorAgent", event_type="handoff", message="start")
    assert len(events) == 1
    assert events[0].agent_name == "StoryDirectorAgent"
    assert events[0].event_type == "handoff"
    assert events[0].message == "start"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_shared_contracts.py -q
```

Expected: FAIL because `CanonContext` and `AgentTraceEvent` do not exist.

- [ ] **Step 3: Implement shared contracts**

In `backend/app/agents/shared/canon_context.py`:

```python
from __future__ import annotations

from typing import Any

from app.schemas.common import APIModel


class CanonContext(APIModel):
    project_id: str
    project: dict[str, Any] = {}
    story_bible: dict[str, Any] = {}
    characters: list[dict[str, Any]] = []
    world_facts: list[dict[str, Any]] = []
    story_entities: list[dict[str, Any]] = []
    graph: dict[str, Any] = {}
    previous_summaries: list[dict[str, Any]] = []
    continuity_issues: list[dict[str, Any]] = []
```

In `backend/app/agents/shared/trace.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schemas.common import APIModel


class AgentTraceEvent(APIModel):
    timestamp: str
    agent_name: str
    event_type: str
    message: str
    payload: dict[str, Any] = {}


def append_trace(
    events: list[AgentTraceEvent],
    *,
    agent_name: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> AgentTraceEvent:
    event = AgentTraceEvent(
        timestamp=datetime.now(UTC).isoformat(),
        agent_name=agent_name,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    events.append(event)
    return event
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_shared_contracts.py -q
```

Expected: PASS.

---

### Task 3: Outline Swarm State And Stop Validator

**Files:**
- Create/modify: `backend/app/agents/outline_swarm/state.py`
- Create/modify: `backend/app/agents/outline_swarm/validators.py`
- Test: `backend/tests/test_outline_swarm_state.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_outline_swarm_state.py`:

```python
from __future__ import annotations

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.validators import OutlineSwarmStopValidator


def test_outline_swarm_state_has_safe_defaults() -> None:
    state = OutlineSwarmState(project_id="prj_test")
    assert state.active_agent == "StoryDirectorAgent"
    assert state.iteration_count == 0
    assert state.max_iterations == 8
    assert state.status == "running"
    assert state.volume_outlines == []


def test_stop_validator_passes_when_requirements_met() -> None:
    state = OutlineSwarmState(
        project_id="prj_test",
        volume_target=1,
        chapter_target=2,
        volume_outlines=[{"volume_no": 1}],
        chapter_beats=[{"chapter_no": 1}, {"chapter_no": 2}],
        continuity_issues=[],
        incomplete_required_entities=[],
    )
    result = OutlineSwarmStopValidator().evaluate(state)
    assert result.should_stop is True
    assert result.status == "passed"


def test_stop_validator_loops_when_blocking_issues_exist() -> None:
    state = OutlineSwarmState(
        project_id="prj_test",
        continuity_issues=[{"severity": "blocking", "message": "S级实体缺档案"}],
    )
    result = OutlineSwarmStopValidator().evaluate(state)
    assert result.should_stop is False
    assert result.status == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_state.py -q
```

Expected: FAIL because state and validator are not implemented.

- [ ] **Step 3: Implement state and validator**

In `backend/app/agents/outline_swarm/state.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from app.agents.shared.canon_context import CanonContext
from app.agents.shared.trace import AgentTraceEvent
from app.schemas.common import APIModel


class OutlineSwarmState(APIModel):
    project_id: str
    seed: dict[str, Any] = {}
    canon_context: CanonContext | None = None
    story_bible: dict[str, Any] = {}
    characters: list[dict[str, Any]] = []
    story_entities: list[dict[str, Any]] = []
    world_facts: list[dict[str, Any]] = []
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    outline: dict[str, Any] = {}
    volume_outlines: list[dict[str, Any]] = []
    chapter_beats: list[dict[str, Any]] = []
    foreshadowing_items: list[dict[str, Any]] = []
    continuity_issues: list[dict[str, Any]] = []
    completion_tickets: list[dict[str, Any]] = []
    uncertainty_tickets: list[dict[str, Any]] = []
    incomplete_required_entities: list[dict[str, Any]] = []
    active_agent: str = "StoryDirectorAgent"
    agent_trace: list[AgentTraceEvent] = []
    iteration_count: int = 0
    max_iterations: int = 8
    volume_target: int = 1
    chapter_target: int = 10
    status: Literal["running", "passed", "failed", "needs_user_review"] = "running"
```

In `backend/app/agents/outline_swarm/validators.py`:

```python
from __future__ import annotations

from typing import Literal

from app.agents.outline_swarm.state import OutlineSwarmState
from app.schemas.common import APIModel


class OutlineSwarmStopResult(APIModel):
    should_stop: bool
    status: Literal["running", "passed", "failed", "needs_user_review"]
    reasons: list[str]


class OutlineSwarmStopValidator:
    def evaluate(self, state: OutlineSwarmState) -> OutlineSwarmStopResult:
        reasons: list[str] = []
        blocking = [issue for issue in state.continuity_issues if issue.get("severity") == "blocking"]
        if blocking:
            reasons.append("存在 blocking continuity issue")
        if state.incomplete_required_entities:
            reasons.append("存在未补全 S/A 级实体")
        if len(state.volume_outlines) < state.volume_target:
            reasons.append("卷纲数量未达标")
        if len(state.chapter_beats) < state.chapter_target:
            reasons.append("章纲/节拍数量未达标")
        if state.iteration_count >= state.max_iterations:
            return OutlineSwarmStopResult(should_stop=True, status="failed", reasons=["达到最大迭代次数", *reasons])
        if reasons:
            return OutlineSwarmStopResult(should_stop=False, status="running", reasons=reasons)
        return OutlineSwarmStopResult(should_stop=True, status="passed", reasons=["大纲 Swarm 停止条件已满足"])
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_state.py -q
```

Expected: PASS.

---

### Task 4: No-Hardcoded-Story Guard For Outline Swarm

**Files:**
- Test: `backend/tests/test_outline_swarm_no_hardcoded_story.py`
- Modify as needed: `backend/app/agents/outline_swarm/*.py`

- [ ] **Step 1: Write failing/passing guard test**

Create `backend/tests/test_outline_swarm_no_hardcoded_story.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ["龙骨能源", "最后真龙封印", "帝国能源署", "龙骨矿区", "最后龙裔矿工"]


def test_outline_swarm_does_not_hardcode_sample_story_content() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend/app/agents/outline_swarm").glob("**/*.py")
    )
    for forbidden in FORBIDDEN:
        assert forbidden not in source
```

- [ ] **Step 2: Run test**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_no_hardcoded_story.py -q
```

Expected: PASS for new files. This test guards future changes.

---

### Task 5: Outline Swarm Tools

**Files:**
- Create/modify: `backend/app/agents/outline_swarm/tools.py`
- Test: `backend/tests/test_outline_swarm_tools.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_outline_swarm_tools.py`:

```python
from __future__ import annotations

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.tools import (
    create_completion_ticket,
    create_uncertainty_ticket,
    record_outline_piece,
    upsert_canon_candidate,
)


def test_tools_write_to_state_not_database() -> None:
    state = OutlineSwarmState(project_id="prj_test")
    upsert_canon_candidate(state, {"name": "候选城市", "entity_type": "location", "confidence": 0.72})
    create_completion_ticket(state, {"entity_name": "候选城市", "entity_level": "A"})
    create_uncertainty_ticket(state, "为什么主角必须进入候选城市？")
    record_outline_piece(state, "volume", {"volume_no": 1, "title": "第一卷"})
    assert state.story_entities[0]["name"] == "候选城市"
    assert state.completion_tickets[0]["entity_name"] == "候选城市"
    assert state.uncertainty_tickets[0]["question"] == "为什么主角必须进入候选城市？"
    assert state.volume_outlines[0]["title"] == "第一卷"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_tools.py -q
```

Expected: FAIL because tools are not implemented.

- [ ] **Step 3: Implement tools**

In `backend/app/agents/outline_swarm/tools.py`:

```python
from __future__ import annotations

from typing import Any

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.shared.trace import append_trace


def upsert_canon_candidate(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = {**payload, "source": "outline_swarm", "status": "candidate"}
    state.story_entities.append(candidate)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="canon_candidate", message="写入候选正典", payload=candidate)
    return candidate


def create_completion_ticket(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    ticket = {**payload, "source": "outline_swarm", "status": "open"}
    state.completion_tickets.append(ticket)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="completion_ticket", message="创建实体补全任务", payload=ticket)
    return ticket


def create_uncertainty_ticket(state: OutlineSwarmState, question: str) -> dict[str, Any]:
    ticket = {"question": question, "source": "outline_swarm", "status": "open"}
    state.uncertainty_tickets.append(ticket)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="uncertainty_ticket", message=question, payload=ticket)
    return ticket


def record_outline_piece(state: OutlineSwarmState, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "outline":
        state.outline.update(payload)
    elif kind == "volume":
        state.volume_outlines.append(payload)
    elif kind == "chapter":
        state.chapter_beats.append(payload)
    elif kind == "foreshadowing":
        state.foreshadowing_items.append(payload)
    else:
        raise ValueError(f"未知大纲片段类型：{kind}")
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="outline_piece", message=f"记录 {kind}", payload=payload)
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_tools.py -q
```

Expected: PASS.

---

### Task 6: Outline Swarm Builder With Fallback

**Files:**
- Create/modify: `backend/app/agents/outline_swarm/swarm.py`
- Create/modify: `backend/app/agents/outline_swarm/service.py`
- Test: `backend/tests/test_outline_swarm_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_outline_swarm_service.py`:

```python
from __future__ import annotations

from app.agents.outline_swarm.service import run_outline_swarm


def test_run_outline_swarm_returns_structured_result_without_api_key() -> None:
    result = run_outline_swarm(
        {
            "project_id": "prj_test",
            "seed": {"genre": "都市脑洞", "premise": "一个普通人发现城市规则正在重写现实。"},
            "volume_target": 1,
            "chapter_target": 2,
        }
    )
    assert result["project_id"] == "prj_test"
    assert result["status"] in {"passed", "needs_user_review", "failed"}
    assert result["outline"]
    assert result["volume_outlines"]
    assert result["chapter_beats"]
    assert result["agent_trace"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_service.py -q
```

Expected: FAIL because service does not return structured result.

- [ ] **Step 3: Implement fallback service**

In `backend/app/agents/outline_swarm/service.py`:

```python
from __future__ import annotations

from typing import Any

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.tools import create_completion_ticket, record_outline_piece, upsert_canon_candidate
from app.agents.outline_swarm.validators import OutlineSwarmStopValidator
from app.agents.shared.trace import append_trace


def run_outline_swarm(payload: dict[str, Any]) -> dict[str, Any]:
    state = OutlineSwarmState(
        project_id=payload["project_id"],
        seed=payload.get("seed", {}),
        volume_target=int(payload.get("volume_target", 1)),
        chapter_target=int(payload.get("chapter_target", 10)),
    )
    append_trace(state.agent_trace, agent_name="StoryDirectorAgent", event_type="start", message="启动大纲 Swarm 回退流程")
    state.active_agent = "WorldBuilderAgent"
    upsert_canon_candidate(state, {"name": "核心世界规则", "entity_type": "world_fact", "confidence": 0.65})
    create_completion_ticket(state, {"entity_name": "核心世界规则", "entity_level": "A"})
    state.active_agent = "PlotArchitectAgent"
    record_outline_piece(state, "outline", {"title": "全书总纲", "premise": state.seed.get("premise", "")})
    for volume_no in range(1, state.volume_target + 1):
        record_outline_piece(state, "volume", {"volume_no": volume_no, "title": f"第{volume_no}卷", "core_goal": "推进主线并扩展世界规则"})
    for chapter_no in range(1, state.chapter_target + 1):
        record_outline_piece(state, "chapter", {"chapter_no": chapter_no, "title": f"第{chapter_no}章", "story_function": "目标、阻力、转折、钩子"})
    state.incomplete_required_entities = []
    stop = OutlineSwarmStopValidator().evaluate(state)
    state.status = stop.status
    append_trace(state.agent_trace, agent_name="ContinuityAgent", event_type="stop_check", message="完成停止条件检查", payload=stop.model_dump())
    return state.model_dump(mode="json")
```

In `backend/app/agents/outline_swarm/swarm.py`, add a guarded builder that can be expanded later:

```python
from __future__ import annotations

from typing import Any


def build_outline_swarm(*_: Any, **__: Any) -> Any:
    try:
        from langgraph_swarm import create_swarm  # noqa: F401
    except Exception as exc:
        raise RuntimeError("langgraph_swarm 不可用，请安装 langgraph-swarm 或使用 run_outline_swarm 回退服务。") from exc
    raise NotImplementedError("真实 Swarm Agent 接入将在服务回退流程通过测试后实现。")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_outline_swarm_service.py -q
```

Expected: PASS.

---

### Task 7: Chapter Writing Lane Wrapper

**Files:**
- Modify: `backend/app/agents/chapter_writing/workflow.py`
- Modify: `backend/app/agents/chapter_writing/service.py`
- Test: `backend/tests/test_chapter_writing_lane_contract.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_chapter_writing_lane_contract.py`:

```python
from __future__ import annotations


def test_chapter_writing_lane_exports_agent_workflow() -> None:
    from app.agents.chapter_writing.workflow import agent_workflow

    assert hasattr(agent_workflow, "run_chapter_draft")
    assert hasattr(agent_workflow, "run_chapter_plan")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_chapter_writing_lane_contract.py -q
```

Expected: FAIL until wrapper exists.

- [ ] **Step 3: Add wrapper**

In `backend/app/agents/chapter_writing/workflow.py`:

```python
from __future__ import annotations

from app.agents.workflow import AgentWorkflow, agent_workflow

__all__ = ["AgentWorkflow", "agent_workflow"]
```

In `backend/app/agents/chapter_writing/service.py`:

```python
from __future__ import annotations

from app.agents.chapter_writing.workflow import agent_workflow

__all__ = ["agent_workflow"]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_chapter_writing_lane_contract.py -q
```

Expected: PASS.

---

### Task 8: Creation Star Lane Wrapper

**Files:**
- Modify: `backend/app/agents/creation_star/state.py`
- Modify: `backend/app/agents/creation_star/service.py`
- Test: `backend/tests/test_creation_star_lane_contract.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_creation_star_lane_contract.py`:

```python
from __future__ import annotations

from app.agents.creation_star.state import CreationStarState
from app.agents.creation_star.service import build_creation_star_state


def test_creation_star_state_tracks_steps() -> None:
    state = build_creation_star_state(project_id="prj_test", current_step="worldview")
    assert isinstance(state, CreationStarState)
    assert state.project_id == "prj_test"
    assert state.current_step == "worldview"
    assert state.confirmed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_creation_star_lane_contract.py -q
```

Expected: FAIL until Creation Star state exists.

- [ ] **Step 3: Implement Creation Star state**

In `backend/app/agents/creation_star/state.py`:

```python
from __future__ import annotations

from typing import Any

from app.schemas.common import APIModel


class CreationStarState(APIModel):
    project_id: str
    current_step: str
    previous_steps: dict[str, Any] = {}
    candidate_cards: list[dict[str, Any]] = []
    selected_payload: dict[str, Any] = {}
    confirmed: bool = False
```

In `backend/app/agents/creation_star/service.py`:

```python
from __future__ import annotations

from typing import Any

from app.agents.creation_star.state import CreationStarState


def build_creation_star_state(project_id: str, current_step: str, previous_steps: dict[str, Any] | None = None) -> CreationStarState:
    return CreationStarState(project_id=project_id, current_step=current_step, previous_steps=previous_steps or {})
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_creation_star_lane_contract.py -q
```

Expected: PASS.

---

### Task 9: Documentation Update

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Test: `frontend/tests/frontend-contract.test.mjs` or new backend doc contract

- [ ] **Step 1: Add doc contract**

Add to `backend/tests/test_agents_three_lanes_contract.py`:

```python
def test_docs_describe_three_agent_lanes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    codex = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for doc in [readme, codex]:
        assert "creation_star" in doc
        assert "outline_swarm" in doc
        assert "chapter_writing" in doc
        assert "langgraph-swarm" in doc
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_three_lanes_contract.py::test_docs_describe_three_agent_lanes -q
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update docs**

Add a short section to README and Codex:

```markdown
## Agent 三线架构

- `backend/app/agents/creation_star/`：抽卡式立项，只生成候选设定，用户确认后写入正式项目。
- `backend/app/agents/outline_swarm/`：大纲生成与世界构建，使用 `langgraph-swarm` 做动态 handoff 和有限循环。
- `backend/app/agents/chapter_writing/`：章节正文生成，使用稳定 LangGraph StateGraph 和质量门修订循环。
```

- [ ] **Step 4: Run doc test**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests/test_agents_three_lanes_contract.py::test_docs_describe_three_agent_lanes -q
```

Expected: PASS.

---

### Task 10: Full Verification

**Files:** no new files.

- [ ] **Step 1: Run backend tests**

Run:

```bash
/opt/miniconda3/bin/python3 -m pytest backend/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs test
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
node ../.codex-tools/pnpm-11.5.1/bin/pnpm.cjs build
```

Expected: TypeScript compile and Vite build succeed. Large chunk warnings are acceptable unless a new warning appears.

- [ ] **Step 4: Record results**

Update final response with:

```text
后端测试：x passed
前端测试：x passed
前端构建：passed
已知限制：真实 langgraph_swarm Agent 接入仍在后续阶段，当前实现含 fallback skeleton
```
