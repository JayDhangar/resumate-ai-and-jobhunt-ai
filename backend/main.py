"""Resume Builder AI — FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes_generate import router as generate_router
from api.routes_jobs import router as jobs_router
from api.routes_resumes import router as resumes_router
from api.routes_templates import router as templates_router
from core.config import get_settings
from core.exceptions import ResumeBuilderError
from core.logging_config import configure_logging, get_logger

logger = get_logger("main")


async def _periodic_template_search(interval_minutes: int) -> None:
    """Background task: periodically refresh the template library."""
    from agents.coordinator import get_coordinator

    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            result = await asyncio.to_thread(get_coordinator().refresh_templates)
            logger.info("Periodic template search: %s", result.get("detail", ""))
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.warning("Periodic template search failed: %s", exc)


async def _job_alerts_loop() -> None:
    """Run due job alerts once per day (per saved search), after the configured hour."""
    import datetime as dt

    from agents.job_alerts_agent import get_job_alerts_agent

    settings = get_settings()
    while True:
        try:
            await asyncio.sleep(15 * 60)  # check every 15 minutes; run_due skips completed days
            if dt.datetime.now().hour >= settings.job_alerts_hour:
                result = await asyncio.to_thread(get_job_alerts_agent().run_due)
                if result["ran"]:
                    logger.info("Job alerts: ran %d search(es)", result["ran"])
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.warning("Job alerts loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.debug)
    from agents.coordinator import get_coordinator

    # seed the template library on boot (web search is best-effort)
    try:
        await asyncio.to_thread(get_coordinator().refresh_templates)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Initial template refresh failed: %s", exc)

    search_task: asyncio.Task | None = None
    if settings.template_search_enabled:
        search_task = asyncio.create_task(
            _periodic_template_search(settings.template_search_interval_minutes)
        )
    alerts_task = asyncio.create_task(_job_alerts_loop())
    logger.info("%s backend ready", settings.app_name)
    yield
    if search_task is not None:
        search_task.cancel()
    alerts_task.cancel()


app = FastAPI(
    title="Resume Builder AI",
    description="Multi-agent AI resume builder: read, search, parse, edit, generate, export.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ResumeBuilderError)
async def domain_error_handler(_: Request, exc: ResumeBuilderError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/r/{slug}")
def public_resume(slug: str):
    """Public resume page — live-rendered with the owner's selected template."""
    from fastapi.responses import HTMLResponse

    from agents.coordinator import get_coordinator
    from core.exceptions import NotFoundError

    coordinator = get_coordinator()
    record = next((r for r in coordinator.list_resumes() if r.public_slug == slug), None)
    if record is None:
        raise NotFoundError("This resume is not published (or the link was disabled).")
    template = coordinator._maybe_template(record.selected_template_id) or coordinator.list_templates()[0]
    html = coordinator.generator.render_html(record.data, template)
    footer = (
        '<div style="text-align:center;padding:14px;font-family:sans-serif;font-size:11px;color:#888">'
        'Live resume · built with <strong>ResuMate AI</strong></div>'
    )
    return HTMLResponse(html.replace("</body>", footer + "</body>"))


@app.get("/api/usage")
def usage():
    """Cumulative LLM token usage and estimated cost, grouped by operation."""
    from services.usage_tracker import get_usage

    return get_usage()


@app.get("/api/health")
def health():
    from services.llm_service import get_llm

    settings = get_settings()
    llm = get_llm()
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_available": llm.available,
        "llm_provider": llm.provider.name if llm.provider else "none",
        "storage": "mongodb" if settings.mongodb_url else "sqlite",
    }


app.include_router(resumes_router)
app.include_router(templates_router)
app.include_router(generate_router)
app.include_router(jobs_router)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
