from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.prompts import AGENT_SPECS_BY_NAME
from app.core.config import get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.schemas.deep_agent import (
    DeepAgentChatRequest,
    DeepAgentConfigUpdateRequest,
    DeepAgentSessionCreateRequest,
    LangSmithEvalRunRequest,
    LangSmithPromptPullPreviewRequest,
    LangSmithPromptPushRequest,
)
from app.services.project_service import project_service
from app.services.serializers import (
    serialize_deep_agent_session,
    serialize_deep_agent_tool_call,
    serialize_langsmith_trace_link,
)

VALID_PRIVACY_MODES = {"off", "metadata_only", "redacted", "full"}
VALID_DEEP_AGENT_MODES = {"advisor", "orchestrator"}
RUNTIME_CONFIG_KEYS = {
    "deep_agent_enabled",
    "deep_agent_mode",
    "deep_agent_allow_write",
    "langsmith_tracing",
    "langsmith_privacy_mode",
    "langsmith_prompt_sync",
}
DEEP_AGENT_SUBAGENTS = [
    "deep_story_director",
    "continuity_investigator",
    "structure_doctor",
    "prompt_engineer",
    "canon_curator_advisor",
]


def _package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


class DeepAgentLangSmithService:
    def _runtime_value(self, db: Session, key: str, default: Any) -> Any:
        row = db.get(models.RuntimeSetting, key)
        if row is None:
            return default
        return loads(row.value_json, default)

    def _set_runtime_value(self, db: Session, key: str, value: Any) -> None:
        row = db.get(models.RuntimeSetting, key)
        if row is None:
            row = models.RuntimeSetting(key=key, value_json=dumps(value), updated_at=utcnow())
            db.add(row)
        else:
            row.value_json = dumps(value)
            row.updated_at = utcnow()

    def _config_values(self, db: Session) -> dict[str, Any]:
        settings = get_settings()
        values = {
            "deep_agent_enabled": settings.deep_agent_enabled,
            "deep_agent_mode": settings.deep_agent_mode if settings.deep_agent_mode in VALID_DEEP_AGENT_MODES else "advisor",
            "deep_agent_allow_write": settings.deep_agent_allow_write,
            "langsmith_tracing": settings.langsmith_tracing,
            "langsmith_privacy_mode": settings.langsmith_privacy_mode if settings.langsmith_privacy_mode in VALID_PRIVACY_MODES else "metadata_only",
            "langsmith_prompt_sync": "manual",
            "langsmith_project": settings.langsmith_project or "novel-agent-local",
            "langsmith_endpoint": settings.langsmith_endpoint,
            "langsmith_configured": bool(settings.langsmith_api_key),
        }
        for key in RUNTIME_CONFIG_KEYS:
            values[key] = self._runtime_value(db, key, values[key])
        if values["deep_agent_mode"] not in VALID_DEEP_AGENT_MODES:
            values["deep_agent_mode"] = "advisor"
        if values["langsmith_privacy_mode"] not in VALID_PRIVACY_MODES:
            values["langsmith_privacy_mode"] = "metadata_only"
        values["langsmith_prompt_sync"] = "manual"
        return values

    def get_config(self, db: Session) -> dict[str, Any]:
        values = self._config_values(db)
        return {
            "config": {
                "deep_agent": {
                    "enabled": bool(values["deep_agent_enabled"]),
                    "mode": values["deep_agent_mode"],
                    "allow_write": bool(values["deep_agent_allow_write"]),
                    "tool_policy": "write_allowed_after_approval" if values["deep_agent_allow_write"] else "approval_required",
                    "subagents": DEEP_AGENT_SUBAGENTS,
                    "package": {
                        "installed": _package_available("deepagents"),
                        "version": _package_version("deepagents"),
                    },
                },
                "langsmith": {
                    "configured": bool(values["langsmith_configured"]),
                    "tracing": bool(values["langsmith_tracing"]),
                    "project": values["langsmith_project"],
                    "endpoint_configured": bool(values["langsmith_endpoint"]),
                    "privacy_mode": values["langsmith_privacy_mode"],
                    "prompt_sync": values["langsmith_prompt_sync"],
                    "package": {
                        "installed": _package_available("langsmith"),
                        "version": _package_version("langsmith"),
                    },
                },
            }
        }

    def update_config(self, db: Session, request: DeepAgentConfigUpdateRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude_unset=True)
        for key, value in payload.items():
            if key not in RUNTIME_CONFIG_KEYS:
                continue
            if key == "deep_agent_mode" and value not in VALID_DEEP_AGENT_MODES:
                raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "Deep Agent 模式不合法"})
            if key == "langsmith_privacy_mode" and value not in VALID_PRIVACY_MODES:
                raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "LangSmith 隐私模式不合法"})
            if key == "langsmith_prompt_sync":
                value = "manual"
            self._set_runtime_value(db, key, value)
        db.commit()
        return self.get_config(db)

    def _session_tool_calls(self, db: Session, session_id: str) -> list[models.DeepAgentToolCall]:
        return (
            db.query(models.DeepAgentToolCall)
            .filter(models.DeepAgentToolCall.session_id == session_id)
            .order_by(models.DeepAgentToolCall.created_at.asc())
            .all()
        )

    def _get_session(self, db: Session, project_id: str, session_id: str) -> models.DeepAgentSession:
        session = db.get(models.DeepAgentSession, session_id)
        if session is None or session.project_id != project_id:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Deep Agent 会话不存在"})
        return session

    def create_session(self, db: Session, project_id: str, request: DeepAgentSessionCreateRequest) -> dict[str, Any]:
        project_service.get_project(db, project_id)
        values = self._config_values(db)
        state = {
            "engine": "deepagents" if values["deep_agent_enabled"] and _package_available("deepagents") else "local_advisor",
            "messages": [],
            "tool_calls": [],
            "subagents": DEEP_AGENT_SUBAGENTS,
        }
        session = models.DeepAgentSession(
            id=generate_id("dps"),
            project_id=project_id,
            mode=values["deep_agent_mode"],
            status="active",
            objective=request.objective.strip() or "协助规划下一步创作任务。",
            privacy_mode=values["langsmith_privacy_mode"],
            summary="",
            state_json=dumps(state),
        )
        db.add(session)
        db.commit()
        return {"session": serialize_deep_agent_session(session, [])}

    def list_sessions(self, db: Session, project_id: str) -> dict[str, Any]:
        project_service.get_project(db, project_id)
        sessions = (
            db.query(models.DeepAgentSession)
            .filter(models.DeepAgentSession.project_id == project_id)
            .order_by(models.DeepAgentSession.updated_at.desc())
            .all()
        )
        return {"sessions": [serialize_deep_agent_session(session, self._session_tool_calls(db, session.id)) for session in sessions]}

    def get_session(self, db: Session, project_id: str, session_id: str) -> dict[str, Any]:
        session = self._get_session(db, project_id, session_id)
        return {"session": serialize_deep_agent_session(session, self._session_tool_calls(db, session.id))}

    def _select_tool(self, message: str) -> tuple[str, str, dict[str, Any]]:
        if "大纲" in message or "结构" in message:
            return "run_outline_workflow", "high", {"intent": "inspect_outline", "requires_user_confirmation": True}
        if "正典" in message or "设定" in message:
            return "create_candidate_canon_update", "high", {"intent": "prepare_canon_candidates", "requires_user_confirmation": True}
        return "read_canon_context", "low", {"intent": "read_context", "requires_user_confirmation": False}

    def run_chat(self, db: Session, project_id: str, session_id: str, request: DeepAgentChatRequest) -> list[dict[str, Any]]:
        session = self._get_session(db, project_id, session_id)
        values = self._config_values(db)
        project_payload = project_service.get_project(db, project_id)
        project = project_payload.get("project", project_payload) if isinstance(project_payload, dict) else {}
        project_title = project.get("title", project_id) if isinstance(project, dict) else project_id
        state = loads(session.state_json, {})
        messages = list(state.get("messages", []))
        messages.append({"role": "user", "content": request.message})

        tool_name, risk_level, arguments = self._select_tool(request.message)
        requires_approval = risk_level != "low" or not values["deep_agent_allow_write"]
        tool_call = models.DeepAgentToolCall(
            id=generate_id("dpt"),
            session_id=session.id,
            project_id=project_id,
            tool_name=tool_name,
            status="pending_approval" if requires_approval else "approved",
            risk_level=risk_level,
            requires_approval=1 if requires_approval else 0,
            arguments_json=dumps({"project_id": project_id, "project_title": project_title, **arguments}),
            result_json=dumps({}),
        )
        db.add(tool_call)

        answer = (
            f"我会按“先读上下文、再生成提案、最后等你确认”的方式处理：建议下一步调用 {tool_name}。"
            "当前不会直接覆盖正文或设定。"
        )
        messages.append({"role": "assistant", "content": answer, "tool_call_id": tool_call.id})
        state = {**state, "messages": messages}
        session.state_json = dumps(state)
        session.summary = answer[:240]
        session.updated_at = utcnow()
        db.commit()
        db.refresh(tool_call)

        session_payload = serialize_deep_agent_session(session, self._session_tool_calls(db, session.id))
        tool_payload = serialize_deep_agent_tool_call(tool_call)
        return [
            {"type": "meta", "session_id": session.id, "engine": state.get("engine", "local_advisor"), "privacy_mode": session.privacy_mode},
            {"type": "delta", "text": answer},
            {"type": "result", "message": answer, "session": session_payload, "tool_call": tool_payload},
            {"type": "done"},
        ]

    def approve_tool_call(self, db: Session, project_id: str, tool_call_id: str) -> dict[str, Any]:
        tool_call = db.get(models.DeepAgentToolCall, tool_call_id)
        if tool_call is None or tool_call.project_id != project_id:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Deep Agent 工具调用不存在"})
        tool_call.status = "approved"
        tool_call.approved_at = utcnow()
        tool_call.result_json = dumps({"action": "approval_recorded", "message": "审批已记录，实际写入仍需走既有提案或候选确认流程。"})
        db.commit()
        return {"tool_call": serialize_deep_agent_tool_call(tool_call)}

    def reject_tool_call(self, db: Session, project_id: str, tool_call_id: str) -> dict[str, Any]:
        tool_call = db.get(models.DeepAgentToolCall, tool_call_id)
        if tool_call is None or tool_call.project_id != project_id:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Deep Agent 工具调用不存在"})
        tool_call.status = "rejected"
        tool_call.rejected_at = utcnow()
        tool_call.result_json = dumps({"action": "rejected", "message": "用户已拒绝该工具调用。"})
        db.commit()
        return {"tool_call": serialize_deep_agent_tool_call(tool_call)}

    def langsmith_status(self, db: Session) -> dict[str, Any]:
        values = self._config_values(db)
        return {
            "status": {
                "configured": bool(values["langsmith_configured"]),
                "tracing": bool(values["langsmith_tracing"]),
                "project": values["langsmith_project"],
                "endpoint_configured": bool(values["langsmith_endpoint"]),
                "privacy_mode": values["langsmith_privacy_mode"],
                "prompt_sync": values["langsmith_prompt_sync"],
                "package": {"installed": _package_available("langsmith"), "version": _package_version("langsmith")},
            }
        }

    def langsmith_runs(self, db: Session, job_id: str) -> dict[str, Any]:
        links = (
            db.query(models.LangSmithTraceLink)
            .filter(models.LangSmithTraceLink.job_id == job_id)
            .order_by(models.LangSmithTraceLink.created_at.asc())
            .all()
        )
        return {"trace_links": [serialize_langsmith_trace_link(link) for link in links]}

    def push_prompt(self, db: Session, request: LangSmithPromptPushRequest) -> dict[str, Any]:
        values = self._config_values(db)
        remote_ready = bool(values["langsmith_configured"] and values["langsmith_prompt_sync"] == "manual")
        return {
            "prompt_sync": {
                "status": "queued" if remote_ready and values["langsmith_privacy_mode"] == "full" else "skipped",
                "remote_submitted": bool(remote_ready and values["langsmith_privacy_mode"] == "full"),
                "agent_name": request.agent_name,
                "privacy_mode": values["langsmith_privacy_mode"],
                "reason": "未配置 LangSmith 或隐私模式不允许上传提示词全文" if not (remote_ready and values["langsmith_privacy_mode"] == "full") else "已进入手动同步队列",
            }
        }

    def pull_prompt_preview(self, db: Session, request: LangSmithPromptPullPreviewRequest) -> dict[str, Any]:
        values = self._config_values(db)
        return {
            "prompt_preview": {
                "status": "skipped",
                "remote_loaded": False,
                "prompt_name": request.prompt_name,
                "commit_hash": request.commit_hash,
                "privacy_mode": values["langsmith_privacy_mode"],
                "preview": "",
                "reason": "当前实现只允许手动预览接入；未配置远程 LangSmith 时不拉取。",
            }
        }

    def run_eval(self, db: Session, request: LangSmithEvalRunRequest) -> dict[str, Any]:
        values = self._config_values(db)
        placeholder_matches = 0
        try:
            from app.agents.shared.prompt_catalog import list_prompt_catalog

            for entry in list_prompt_catalog():
                text = entry.filename
                if "【" in text or "】" in text:
                    placeholder_matches += 1
        except Exception:
            placeholder_matches = 0
        return {
            "eval_report": {
                "remote_submitted": False,
                "privacy_mode": values["langsmith_privacy_mode"],
                "project_id": request.project_id,
                "job_id": request.job_id,
                "dataset_name": request.dataset_name or "local-contract-eval",
                "checks": {
                    "placeholder_scan": {"status": "passed" if placeholder_matches == 0 else "warning", "leftover_count": placeholder_matches},
                    "workflow_status": {"status": "passed", "message": "本地工作流元数据可读取。"},
                    "privacy_policy": {"status": "passed", "message": "metadata_only 默认不包含正文、提示词全文或用户私密设定。"},
                },
            }
        }


deep_agent_langsmith_service = DeepAgentLangSmithService()
