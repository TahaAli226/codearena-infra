import os
import secrets
from typing import Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .run_code import run_code

runner_secret = os.environ.get("RUNNER_SECRET_KEY")

app = FastAPI(title="CodeArena Runner")

class CheckRunRequest(BaseModel):
    language: Literal["python", "cpp"]
    code: str = Field(max_length=64 * 1024)
    input: list[str] = Field(min_length=1, max_length=20)
    time_limit_ms: int = Field(default=1000, gt=0, le=20000)
    memory_limit_mb: int = Field(default=256, gt=0, le=256)


@app.post("/run")
def run(request: CheckRunRequest, secret_key: str = Header(default="")):
    if runner_secret:
        if not secrets.compare_digest(secret_key, runner_secret):
            raise HTTPException(status_code=401, detail="Invalid runner secret")
    return run_code(request.language, request.code, request.input, request.time_limit_ms, request.memory_limit_mb)