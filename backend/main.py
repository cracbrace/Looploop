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

def _force_utf8(stream):
    """
    Windows 终端 UTF-8 编码修复。

    优先用 in-place 的 `reconfigure()`：pytest 的捕获对象（`CaptureIO`）本身继承
    `io.TextIOWrapper`，原地改编码不会夺走底层 buffer 的所有权。

    旧写法 `io.TextIOWrapper(stream.buffer)` 会造出第二个持有同一 buffer 的 wrapper：
    pytest 关闭它自己的 wrapper 后，我们那个就指向已关闭的文件，
    导致 teardown 抛 `ValueError: I/O operation on closed file`（pytest 退出码 1）。
    """
    import io

    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
            return stream
        except (ValueError, OSError, AttributeError):
            pass

    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return stream
    try:
        return io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
    except Exception:
        return stream


if sys.platform == "win32":
    sys.stdout = _force_utf8(sys.stdout)
    sys.stderr = _force_utf8(sys.stderr)


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
