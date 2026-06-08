from app.schemas.common import APIModel


class CancelJobRequest(APIModel):
    reason: str = ""
