from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.ids import generate_id


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
        "request_id": generate_id("req"),
        "timestamp": utc_now_iso(),
    }


def error_response(code: str, message: str, details: Any = None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "request_id": generate_id("req"),
            "timestamp": utc_now_iso(),
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        "VALIDATION_ERROR",
        "请求体字段不合法",
        {"errors": exc.errors()},
        status_code=422,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return error_response(
        detail.get("code", "INTERNAL_ERROR"),
        detail.get("message", str(exc.detail)),
        detail.get("details", {}),
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        "INTERNAL_ERROR",
        "服务器内部错误",
        {"reason": str(exc)},
        status_code=500,
    )
