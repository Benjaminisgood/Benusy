import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.core.security import get_password_hash
from app.core.config import settings
from app.db.database import create_db_and_tables, engine
from app.models import PlatformMetricConfig, ReviewStatus, Role, User
from app.routers import admin, assignments, auth, public, tasks, users
from app.services.scheduler import metrics_update_loop

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
static_dir = os.path.join(frontend_dir, "static")


def _seed_default_platform_configs() -> None:
    with Session(engine) as session:
        existing_default = session.exec(
            select(PlatformMetricConfig).where(PlatformMetricConfig.platform == "default")
        ).first()
        if existing_default is None:
            session.add(PlatformMetricConfig(platform="default"))
        for platform in ["douyin", "xiaohongshu", "weibo"]:
            existing = session.exec(
                select(PlatformMetricConfig).where(PlatformMetricConfig.platform == platform)
            ).first()
            if existing is None:
                session.add(PlatformMetricConfig(platform=platform))
        session.commit()


def _seed_default_admin() -> None:
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.role == Role.admin)).first()
        if admin is not None:
            return

        session.add(
            User(
                email="admin@example.com",
                phone="13000000000",
                username="admin",
                display_name="Admin",
                real_name="Platform Admin",
                city="N/A",
                category="operations",
                tags="admin",
                follower_total=0,
                avg_views=0,
                hashed_password=get_password_hash("admin123"),
                role=Role.admin,
                review_status=ReviewStatus.approved,
            )
        )
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    _seed_default_admin()
    _seed_default_platform_configs()

    stop_event = asyncio.Event()
    scheduler_task = None

    if settings.metrics_update_interval_seconds > 0:
        scheduler_task = asyncio.create_task(metrics_update_loop(stop_event))

    try:
        yield
    finally:
        if scheduler_task is not None:
            stop_event.set()
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

for router in (auth.router, users.router, tasks.router, assignments.router, admin.router, public.router):
    app.include_router(router, prefix=settings.api_v1_prefix)


def _serve_html(filename: str, fallback_title: str) -> HTMLResponse:
    path = os.path.join(frontend_dir, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html lang='zh-CN'>
        <head>
            <meta charset='UTF-8'>
            <meta name='viewport' content='width=device-width, initial-scale=1.0'>
            <title>{fallback_title}</title>
        </head>
        <body>
            <div style='text-align:center;padding:50px;'>
                <h1>{fallback_title}</h1>
                <p>页面文件未找到。</p>
                <p><a href='/docs'>API 文档</a></p>
            </div>
        </body>
        </html>
        """
    )


@app.get("/", response_class=HTMLResponse)
def read_root() -> HTMLResponse:
    return _serve_html("index.html", settings.app_name)


@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return _serve_html("login.html", "登录")


@app.get("/auth/register", response_class=HTMLResponse)
def register_page() -> HTMLResponse:
    return _serve_html("register.html", "注册")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
    return _serve_html("dashboard.html", "仪表盘")


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page() -> HTMLResponse:
    return _serve_html("tasks.html", "任务")


@app.get("/assignments", response_class=HTMLResponse)
def assignments_page() -> HTMLResponse:
    return _serve_html("assignments.html", "分配")


@app.get("/profile", response_class=HTMLResponse)
def profile_page() -> HTMLResponse:
    return _serve_html("profile.html", "个人资料")
