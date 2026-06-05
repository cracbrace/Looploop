"""
Looploop（噜噜）— AI 短剧全自动管线
FastAPI 应用入口
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db
from backend.routes import router

# Windows 终端 UTF-8 编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"[Looploop] {settings.app_name} v{settings.app_version} starting...")
    print(f"[Looploop] LLM: {settings.llm_model} @ {settings.llm_base_url}")
    await init_db()
    print(f"[Looploop] Database initialized")
    yield
    print(f"[Looploop] {settings.app_name} shutdown")


app = FastAPI(
    title="Looploop API",
    version=settings.app_version,
    description="AI 短剧全自动管线——将小说文本转化为结构化导演指令",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router)
