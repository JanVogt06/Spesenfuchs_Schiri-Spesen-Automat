"""
Scheduler Package - Automatische Background-Tasks
"""
from scheduler.auto_scrape_scheduler import AutoScrapeScheduler

_scheduler = None


def get_scheduler() -> AutoScrapeScheduler:
    """Gibt die eine Scheduler-Instanz des Prozesses zurueck"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutoScrapeScheduler()
    return _scheduler


__all__ = ['AutoScrapeScheduler', 'get_scheduler']
