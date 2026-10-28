from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import router as api_router
from app.config import get_settings
from app.database import create_schema, engine
from app.middleware import RequestBodyLimitMiddleware

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_schema()
    yield
    await engine.dispose()


app = FastAPI(
    title="ForumScope",
    description="Standalone forum parser and explainable relevance analysis workspace.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=get_settings().max_request_body_bytes)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def workspace(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"request": request})
