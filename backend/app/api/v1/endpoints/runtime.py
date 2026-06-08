from fastapi import HTTPException


def chapter_trace(chapter_id: str):
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "章节追踪接口未纳入本次 MVP 实现"})
