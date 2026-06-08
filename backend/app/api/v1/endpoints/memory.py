from fastapi import HTTPException


def memory_overview(project_id: str):
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "记忆概览接口未纳入本次 MVP 实现"})
