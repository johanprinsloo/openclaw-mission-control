"""
Mock OpenClaw Gateway for POC-6.

Provides:
- /v1/chat  — accepts a message, returns canned agent response
- /v1/command — accepts a command, returns canned output
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock OpenClaw Gateway")


class ChatRequest(BaseModel):
    session_key: str
    message: str
    sender: str = "unknown"


class ChatResponse(BaseModel):
    session_key: str
    response: str


class CommandRequest(BaseModel):
    session_key: str
    command: str
    args: str = ""


class CommandResponse(BaseModel):
    session_key: str
    output: str


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    return ChatResponse(
        session_key=req.session_key,
        response=f"Agent response to: {req.message}",
    )


@app.post("/v1/command", response_model=CommandResponse)
async def command(req: CommandRequest):
    if req.command == "/status":
        output = (
            f"🟢 Status for session {req.session_key}:\n"
            f"  Active tasks: 3\n"
            f"  Pending reviews: 1\n"
            f"  Uptime: 4h 23m"
        )
    else:
        output = f"Unknown command: {req.command}"
    return CommandResponse(session_key=req.session_key, output=output)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-gateway"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8200)
