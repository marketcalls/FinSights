"""
Admin panel routes.
"""
import csv
from datetime import datetime
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from itsdangerous import URLSafeTimedSerializer

from app.database import get_db
from app.config import (
    SECRET_KEY, CATEGORY_NAMES, SUBCATEGORY_NAMES,
    NEWS_SOURCES, TIMEZONE_STR, TIMEZONE
)
from app.models.news import News
from app.models.user import User
from app.models.settings import Setting, ScheduleJob, ApiLog, NewsSource
from app.services.cache import cache_manager
from app.services.perplexity import PerplexityService
from app.services.scheduler import scheduler_service
from app.services.news_fetcher import NewsFetcher

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

# Session serializer
serializer = URLSafeTimedSerializer(SECRET_KEY)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    """Get current logged-in user from session."""
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    try:
        user_id = serializer.loads(session_token, max_age=86400)  # 24 hours
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that requires authentication."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    # Redirect to password change if required (except for the change-password route itself)
    if user.must_change_password and "/change-password" not in str(request.url):
        raise HTTPException(status_code=302, headers={"Location": "/admin/change-password"})
    return user


def flash_message(response: RedirectResponse, message: str, category: str = "info"):
    """Add a flash message to the response (simplified - just for demo)."""
    # In production, use proper flash messages with sessions
    return response


# ============ AUTH ROUTES ============

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Admin login page."""
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process login."""
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.check_password(password):
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    if not user.is_active:
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": "Account is inactive"
        })

    # Create session
    session_token = serializer.dumps(user.id)

    # Check if user must change password (first login with default credentials)
    if user.must_change_password:
        response = RedirectResponse(url="/admin/change-password", status_code=302)
    else:
        response = RedirectResponse(url="/admin/dashboard", status_code=302)

    response.set_cookie("session", session_token, httponly=True, max_age=86400)
    return response


@router.get("/logout")
async def logout():
    """Logout."""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("session")
    return response


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, db: Session = Depends(get_db)):
    """Force password change page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=302)
    if not user.must_change_password:
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    return templates.TemplateResponse("admin/change_password.html", {
        "request": request,
        "current_user": user,
    })


@router.post("/change-password")
async def change_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process forced password change."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=302)

    # Validate passwords match
    if new_password != confirm_password:
        return templates.TemplateResponse("admin/change_password.html", {
            "request": request,
            "current_user": user,
            "error": "Passwords do not match"
        })

    # Validate password strength
    if len(new_password) < 8:
        return templates.TemplateResponse("admin/change_password.html", {
            "request": request,
            "current_user": user,
            "error": "Password must be at least 8 characters long"
        })

    # Update password and clear the flag
    user.set_password(new_password)
    user.must_change_password = False
    db.commit()

    return RedirectResponse(url="/admin/dashboard", status_code=302)


# ============ DASHBOARD ============

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Admin dashboard."""
    # Get stats
    total_news = db.query(News).count()
    today = datetime.now(TIMEZONE).date()
    today_fetches = db.query(ApiLog).filter(
        func.date(ApiLog.timestamp) == today
    ).count()
    active_jobs = db.query(ScheduleJob).filter(ScheduleJob.is_enabled == True).count()

    perplexity = PerplexityService(db)
    api_configured = perplexity.is_configured()

    # Recent news
    recent_news = db.query(News).order_by(desc(News.fetched_at)).limit(10).all()

    # Recent logs
    recent_logs = db.query(ApiLog).order_by(desc(ApiLog.timestamp)).limit(10).all()

    # Category stats
    category_stats = cache_manager.get_cache_stats().get("categories", {})

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "dashboard",
        "current_time": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M IST"),
        "stats": {
            "total_news": total_news,
            "today_fetches": today_fetches,
            "active_jobs": active_jobs,
            "api_configured": api_configured,
        },
        "recent_news": [n.to_dict() for n in recent_news],
        "recent_logs": [l.to_dict() for l in recent_logs],
        "category_stats": category_stats,
    })


# ============ NEWS MANAGEMENT ============

@router.get("/news", response_class=HTMLResponse)
async def news_list(
    request: Request,
    page: int = 1,
    category: str = "",
    status: str = "",
    search: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all news."""
    per_page = 20
    query = db.query(News)

    if category:
        query = query.filter(News.category == category)
    if status == "published":
        query = query.filter(News.is_published == True)
    elif status == "unpublished":
        query = query.filter(News.is_published == False)
    if search:
        query = query.filter(News.title.contains(search))

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    news_items = query.order_by(desc(News.fetched_at)).offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse("admin/news_list.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "news",
        "news_items": [n.to_dict() for n in news_items],
        "page": page,
        "total_pages": total_pages,
        "category": category,
        "status": status,
        "search": search,
        "category_names": CATEGORY_NAMES,
    })


@router.get("/news/create", response_class=HTMLResponse)
async def news_create_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create news page."""
    return templates.TemplateResponse("admin/news_edit.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "news",
        "news": None,
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.post("/news/create")
async def news_create(
    request: Request,
    title: str = Form(...),
    summary: str = Form(...),
    content: str = Form(""),
    category: str = Form(...),
    subcategory: str = Form(""),
    source_name: str = Form(""),
    source_url: str = Form(""),
    symbols: str = Form(""),
    is_published: bool = Form(False),
    is_featured: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create news."""
    news = News(
        title=title,
        summary=summary,
        content=content or None,
        category=category,
        subcategory=subcategory or None,
        source_name=source_name or None,
        source_url=source_url or None,
        symbols=symbols or None,
        is_published=is_published,
        is_featured=is_featured,
        is_manual=True,
        created_by=current_user.id,
        fetched_at=datetime.now(TIMEZONE),
    )
    db.add(news)
    db.commit()

    if is_published:
        cache_manager.add_news(news.to_dict())

    return RedirectResponse(url="/admin/news", status_code=302)


@router.get("/news/{news_id}/edit", response_class=HTMLResponse)
async def news_edit_page(
    request: Request,
    news_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Edit news page."""
    news = db.query(News).filter(News.id == news_id).first()
    if not news:
        return RedirectResponse(url="/admin/news", status_code=302)

    return templates.TemplateResponse("admin/news_edit.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "news",
        "news": news.to_dict(),
        "category_names": CATEGORY_NAMES,
        "subcategory_names": SUBCATEGORY_NAMES,
    })


@router.post("/news/{news_id}/edit")
async def news_edit(
    news_id: int,
    title: str = Form(...),
    summary: str = Form(...),
    content: str = Form(""),
    category: str = Form(...),
    subcategory: str = Form(""),
    source_name: str = Form(""),
    source_url: str = Form(""),
    symbols: str = Form(""),
    is_published: bool = Form(False),
    is_featured: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update news."""
    news = db.query(News).filter(News.id == news_id).first()
    if not news:
        return RedirectResponse(url="/admin/news", status_code=302)

    news.title = title
    news.summary = summary
    news.content = content or None
    news.category = category
    news.subcategory = subcategory or None
    news.source_name = source_name or None
    news.source_url = source_url or None
    news.symbols = symbols or None
    news.is_published = is_published
    news.is_featured = is_featured
    news.updated_at = datetime.now(TIMEZONE)

    db.commit()
    cache_manager.update_news(news_id, news.to_dict())

    return RedirectResponse(url="/admin/news", status_code=302)


@router.post("/news/{news_id}/toggle")
async def news_toggle(
    news_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Toggle news publish status."""
    news = db.query(News).filter(News.id == news_id).first()
    if news:
        news.is_published = not news.is_published
        news.updated_at = datetime.now(TIMEZONE)
        db.commit()

        if news.is_published:
            cache_manager.add_news(news.to_dict())
        else:
            cache_manager.remove_news(news_id)

    return RedirectResponse(url="/admin/news", status_code=302)


@router.post("/news/{news_id}/delete")
async def news_delete(
    news_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete news."""
    news = db.query(News).filter(News.id == news_id).first()
    if news:
        db.delete(news)
        db.commit()
        cache_manager.remove_news(news_id)

    return RedirectResponse(url="/admin/news", status_code=302)


# ============ SCHEDULER ============

@router.get("/scheduler", response_class=HTMLResponse)
async def scheduler_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Scheduler control page."""
    jobs = scheduler_service.get_all_jobs(db)

    return templates.TemplateResponse("admin/scheduler.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "scheduler",
        "jobs": jobs,
        "scheduler_paused": scheduler_service.is_paused(),
        "category_names": CATEGORY_NAMES,
    })


@router.post("/scheduler/job/{job_name}/toggle")
async def scheduler_toggle_job(
    job_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Toggle job enabled status."""
    job = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
    if job:
        scheduler_service.toggle_job(db, job_name, not job.is_enabled)
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/scheduler/job/{job_name}/edit")
async def scheduler_edit_job(
    job_name: str,
    cron_time: str = Form(None),
    interval_minutes: int = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update job timing."""
    scheduler_service.update_job_timing(db, job_name, cron_time, interval_minutes)
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/scheduler/job/{job_name}/run")
async def scheduler_run_job(
    job_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Run a single job now."""
    scheduler_service.run_job_now(db, job_name, f"admin:{current_user.username}")
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/scheduler/run-all")
async def scheduler_run_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Run all enabled jobs now."""
    scheduler_service.run_all_jobs_now(db, f"admin:{current_user.username}")
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/scheduler/pause")
async def scheduler_pause(current_user: User = Depends(require_auth)):
    """Pause scheduler."""
    scheduler_service.pause_all()
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/scheduler/resume")
async def scheduler_resume(current_user: User = Depends(require_auth)):
    """Resume scheduler."""
    scheduler_service.resume_all()
    return RedirectResponse(url="/admin/scheduler", status_code=302)


@router.post("/fetch/custom")
async def fetch_custom(
    query: str = Form(...),
    category: str = Form("market"),
    subcategory: str = Form("custom"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Fetch news with custom query."""
    fetcher = NewsFetcher(db)
    fetcher.fetch_market_summary(
        job_name="custom_fetch",
        query=query,
        category=category,
        subcategory=subcategory or "custom",
        triggered_by=f"admin:{current_user.username}",
    )
    return RedirectResponse(url="/admin/scheduler", status_code=302)


# ============ LOGS ============

@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    page: int = 1,
    event_type: str = "",
    status: str = "",
    job_name: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """API logs viewer."""
    per_page = 50
    query = db.query(ApiLog)

    if event_type:
        query = query.filter(ApiLog.event_type == event_type)
    if status:
        query = query.filter(ApiLog.status == status)
    if job_name:
        query = query.filter(ApiLog.job_name.contains(job_name))

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    logs = query.order_by(desc(ApiLog.timestamp)).offset((page - 1) * per_page).limit(per_page).all()

    # Stats
    total_calls = db.query(ApiLog).count()
    success_calls = db.query(ApiLog).filter(ApiLog.status == "success").count()
    failed_calls = db.query(ApiLog).filter(ApiLog.status == "failed").count()
    avg_response = db.query(func.avg(ApiLog.response_time_ms)).scalar() or 0

    return templates.TemplateResponse("admin/logs.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "logs",
        "logs": [l.to_dict() for l in logs],
        "page": page,
        "total_pages": total_pages,
        "event_type": event_type,
        "status": status,
        "job_name": job_name,
        "stats": {
            "total": total_calls,
            "success": success_calls,
            "failed": failed_calls,
            "avg_response_time": int(avg_response),
        },
    })


@router.get("/logs/export")
async def logs_export(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Export logs as CSV."""
    logs = db.query(ApiLog).order_by(desc(ApiLog.timestamp)).limit(1000).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Event Type", "Job Name", "Query", "Status", "Response Time (ms)", "News Count", "Error", "Triggered By"])

    for log in logs:
        writer.writerow([
            log.timestamp.isoformat() if log.timestamp else "",
            log.event_type,
            log.job_name or "",
            log.query or "",
            log.status,
            log.response_time_ms or "",
            log.news_count or 0,
            log.error_message or "",
            log.triggered_by or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=finsights_logs.csv"}
    )


# ============ SETTINGS ============

def mask_api_key(api_key: str) -> str:
    """Mask API key for display, showing first 5 and last 4 characters."""
    if not api_key or len(api_key) < 12:
        return "****"
    return f"{api_key[:5]}****...****{api_key[-4:]}"


def ensure_default_news_sources(db: Session):
    """Ensure default news sources exist in database."""
    existing_count = db.query(NewsSource).count()
    if existing_count == 0:
        for domain in NEWS_SOURCES:
            source = NewsSource(domain=domain, name=domain.split('.')[0].title(), is_active=True)
            db.add(source)
        db.commit()


def get_news_sources_from_db(db: Session) -> list[dict]:
    """Get all news sources from database."""
    ensure_default_news_sources(db)
    sources = db.query(NewsSource).order_by(NewsSource.is_active.desc(), NewsSource.domain).all()
    return [s.to_dict() for s in sources]


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Settings page."""
    api_key_setting = db.query(Setting).filter(Setting.key == "perplexity_api_key").first()

    api_key_masked = None
    if api_key_setting and api_key_setting.value:
        api_key_masked = mask_api_key(api_key_setting.value)

    # Get news sources from DB
    news_sources = get_news_sources_from_db(db)

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "settings",
        "api_key_set": bool(api_key_setting and api_key_setting.value),
        "api_key_masked": api_key_masked,
        "api_key_updated": api_key_setting.updated_at.strftime("%Y-%m-%d %H:%M") if api_key_setting and api_key_setting.updated_at else None,
        "cache_stats": cache_manager.get_cache_stats(),
        "news_sources": news_sources,
        "timezone": TIMEZONE_STR,
    })


@router.post("/settings/api-key")
async def settings_api_key(
    request: Request,
    api_key: str = Form(...),
    validate_key: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Set or validate API key."""
    perplexity = PerplexityService(db)
    message = None
    message_type = "info"

    if validate_key:
        # Validate and save
        is_valid, validation_msg = perplexity.validate_api_key(api_key)
        if is_valid:
            perplexity.set_api_key(api_key, current_user.id)
            message = f"API key validated and saved! {validation_msg}"
            message_type = "success"
        else:
            message = f"Validation failed: {validation_msg}"
            message_type = "error"
    else:
        # Just save without validation
        perplexity.set_api_key(api_key, current_user.id)
        message = "API key saved successfully!"
        message_type = "success"

    # Re-fetch settings for display
    api_key_setting = db.query(Setting).filter(Setting.key == "perplexity_api_key").first()

    api_key_masked = None
    if api_key_setting and api_key_setting.value:
        api_key_masked = mask_api_key(api_key_setting.value)

    # Get news sources from DB
    news_sources = get_news_sources_from_db(db)

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "settings",
        "api_key_set": bool(api_key_setting and api_key_setting.value),
        "api_key_masked": api_key_masked,
        "api_key_updated": api_key_setting.updated_at.strftime("%Y-%m-%d %H:%M") if api_key_setting and api_key_setting.updated_at else None,
        "cache_stats": cache_manager.get_cache_stats(),
        "news_sources": news_sources,
        "timezone": TIMEZONE_STR,
        "message": message,
        "message_type": message_type,
    })


@router.post("/settings/news-source/add")
async def add_news_source(
    domain: str = Form(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Add a new news source."""
    # Clean domain
    domain = domain.strip().lower()
    if domain.startswith("http://"):
        domain = domain[7:]
    if domain.startswith("https://"):
        domain = domain[8:]
    if domain.startswith("www."):
        domain = domain[4:]
    domain = domain.split("/")[0]  # Remove path

    # Check if exists
    existing = db.query(NewsSource).filter(NewsSource.domain == domain).first()
    if existing:
        return RedirectResponse(url="/admin/settings", status_code=302)

    source = NewsSource(
        domain=domain,
        name=name.strip() or domain.split('.')[0].title(),
        is_active=True
    )
    db.add(source)
    db.commit()

    return RedirectResponse(url="/admin/settings", status_code=302)


@router.post("/settings/news-source/{source_id}/toggle")
async def toggle_news_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Toggle news source active status."""
    source = db.query(NewsSource).filter(NewsSource.id == source_id).first()
    if source:
        source.is_active = not source.is_active
        db.commit()
    return RedirectResponse(url="/admin/settings", status_code=302)


@router.post("/settings/news-source/{source_id}/delete")
async def delete_news_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a news source."""
    source = db.query(NewsSource).filter(NewsSource.id == source_id).first()
    if source:
        db.delete(source)
        db.commit()
    return RedirectResponse(url="/admin/settings", status_code=302)


@router.post("/settings/clear-cache")
async def settings_clear_cache(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Clear cache and reload from database."""
    cache_manager.load_from_db(db)
    return RedirectResponse(url="/admin/settings", status_code=302)


# ============ USERS ============

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Users management page."""
    users = db.query(User).all()

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "current_user": current_user,
        "active_page": "users",
        "users": [u.to_dict() for u in users],
    })


@router.post("/users/create")
async def users_create(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create new admin user."""
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return RedirectResponse(url="/admin/users", status_code=302)

    user = User(username=username)
    user.set_password(password)
    db.add(user)
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/toggle")
async def users_toggle(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Toggle user active status."""
    if user_id == current_user.id:
        return RedirectResponse(url="/admin/users", status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = not user.is_active
        db.commit()

    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/password")
async def users_password(
    user_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Reset user password."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.set_password(password)
        db.commit()

    return RedirectResponse(url="/admin/users", status_code=302)
