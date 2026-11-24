"""
Scheduler package - automatic background tasks
"""
from scheduler.auto_scrape_scheduler import AutoScrapeScheduler

_scheduler = None


def get_scheduler() -> AutoScrapeScheduler:
    """Returns the single scheduler instance of the process"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutoScrapeScheduler()
    return _scheduler


__all__ = ['AutoScrapeScheduler', 'get_scheduler']
