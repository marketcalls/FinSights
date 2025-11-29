"""
APScheduler service for periodic news fetching.
"""
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import TIMEZONE, DEFAULT_SCHEDULE_CONFIG
from app.database import SessionLocal
from app.models.settings import ScheduleJob, ApiLog
from app.services.news_fetcher import NewsFetcher
from app.services.cache import cache_manager


class SchedulerService:
    """Service for managing scheduled news fetching jobs."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)
        self._paused = False
        self._initialized = True

    def _get_db(self) -> Session:
        """Get a new database session."""
        return SessionLocal()

    def _log_event(
        self,
        db: Session,
        event_type: str,
        job_name: Optional[str],
        status: str,
        message: Optional[str] = None,
    ):
        """Log a scheduler event."""
        log = ApiLog(
            timestamp=datetime.now(TIMEZONE),
            event_type=event_type,
            job_name=job_name,
            status=status,
            error_message=message,
            triggered_by="scheduler",
        )
        db.add(log)
        db.commit()

    def _run_job(self, job_name: str):
        """Execute a scheduled job."""
        db = self._get_db()
        try:
            job = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
            if not job or not job.is_enabled:
                return

            fetcher = NewsFetcher(db)
            count = fetcher.fetch_by_job(job, triggered_by="scheduler")

            self._log_event(
                db,
                event_type="scheduler",
                job_name=job_name,
                status="success",
                message=f"Fetched {count} news items",
            )

        except Exception as e:
            self._log_event(
                db,
                event_type="scheduler",
                job_name=job_name,
                status="failed",
                message=str(e),
            )
        finally:
            db.close()

    def init_jobs_from_db(self, db: Session):
        """Initialize scheduler jobs from database."""
        # First, ensure default jobs exist in DB
        self._ensure_default_jobs(db)

        # Load jobs from database
        jobs = db.query(ScheduleJob).filter(ScheduleJob.is_enabled == True).all()

        for job in jobs:
            self._add_job_to_scheduler(job)

    def _ensure_default_jobs(self, db: Session):
        """Ensure default schedule jobs exist in database."""
        for job_name, config in DEFAULT_SCHEDULE_CONFIG.items():
            existing = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
            if not existing:
                job = ScheduleJob(
                    job_name=job_name,
                    category=config["category"],
                    subcategory=config["subcategory"],
                    query_template=config["query"],
                    schedule_type=config["schedule_type"],
                    cron_time=config.get("cron_time"),
                    interval_minutes=config.get("interval_minutes"),
                    is_enabled=config["enabled"],
                )
                db.add(job)
        db.commit()

    def _add_job_to_scheduler(self, job: ScheduleJob):
        """Add a job to the APScheduler."""
        job_id = f"news_{job.job_name}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        if not job.is_enabled:
            return

        if job.schedule_type == "cron" and job.cron_time:
            # Parse cron time (HH:MM)
            hour, minute = map(int, job.cron_time.split(":"))
            trigger = CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE)
        elif job.schedule_type == "interval" and job.interval_minutes:
            trigger = IntervalTrigger(minutes=job.interval_minutes, timezone=TIMEZONE)
        else:
            return

        self.scheduler.add_job(
            self._run_job,
            trigger=trigger,
            args=[job.job_name],
            id=job_id,
            name=f"Fetch {job.job_name}",
            replace_existing=True,
        )

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            self._paused = False

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def pause_all(self):
        """Pause all jobs."""
        self.scheduler.pause()
        self._paused = True

    def resume_all(self):
        """Resume all jobs."""
        self.scheduler.resume()
        self._paused = False

    def is_paused(self) -> bool:
        """Check if scheduler is paused."""
        return self._paused

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running

    def toggle_job(self, db: Session, job_name: str, enabled: bool):
        """Enable or disable a job."""
        job = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
        if job:
            job.is_enabled = enabled
            db.commit()

            if enabled:
                self._add_job_to_scheduler(job)
            else:
                job_id = f"news_{job_name}"
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)

    def update_job_timing(
        self,
        db: Session,
        job_name: str,
        cron_time: Optional[str] = None,
        interval_minutes: Optional[int] = None,
    ):
        """Update job timing."""
        job = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
        if not job:
            return

        if cron_time:
            job.cron_time = cron_time
        if interval_minutes:
            job.interval_minutes = interval_minutes

        db.commit()

        # Reschedule job
        self._add_job_to_scheduler(job)

    def run_job_now(self, db: Session, job_name: str, triggered_by: str = "manual") -> dict:
        """Run a job immediately."""
        job = db.query(ScheduleJob).filter(ScheduleJob.job_name == job_name).first()
        if not job:
            return {"error": "Job not found", "success": False}

        try:
            fetcher = NewsFetcher(db)
            count = fetcher.fetch_by_job(job, triggered_by=triggered_by)
            return {"success": True, "news_count": count}
        except Exception as e:
            return {"error": str(e), "success": False}

    def run_all_jobs_now(self, db: Session, triggered_by: str = "manual") -> dict:
        """Run all enabled jobs immediately."""
        jobs = db.query(ScheduleJob).filter(ScheduleJob.is_enabled == True).all()
        results = {"success": 0, "failed": 0, "total_news": 0}

        for job in jobs:
            try:
                fetcher = NewsFetcher(db)
                count = fetcher.fetch_by_job(job, triggered_by=triggered_by)
                results["success"] += 1
                results["total_news"] += count
            except Exception as e:
                results["failed"] += 1

        return results

    def get_all_jobs(self, db: Session) -> list[dict]:
        """Get all jobs with their status."""
        jobs = db.query(ScheduleJob).all()
        result = []

        for job in jobs:
            job_dict = job.to_dict()

            # Get next run time from scheduler (if available)
            try:
                job_id = f"news_{job.job_name}"
                scheduler_job = self.scheduler.get_job(job_id)
                if scheduler_job:
                    next_run = getattr(scheduler_job, 'next_run_time', None)
                    if next_run:
                        job_dict["next_run"] = next_run.isoformat()
            except Exception:
                pass  # Scheduler may not be running

            result.append(job_dict)

        return result


# Singleton instance
scheduler_service = SchedulerService()
