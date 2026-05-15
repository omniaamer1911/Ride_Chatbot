from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="External user id from your auth layer")
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    reply_ar: str
    ok: bool = True
