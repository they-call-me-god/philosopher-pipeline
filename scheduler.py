import os
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

log = logging.getLogger(__name__)

# Optimal Instagram posting slots: (weekday, hour, minute)
# weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat
POSTING_SLOTS = [
    (1, 9, 0),    # Tuesday 9am
    (1, 12, 0),   # Tuesday 12pm
    (2, 11, 0),   # Wednesday 11am
    (2, 19, 0),   # Wednesday 7pm
    (3, 12, 0),   # Thursday 12pm
    (3, 19, 0),   # Thursday 7pm
    (4, 9, 0),    # Friday 9am
    (4, 12, 0),   # Friday 12pm
    (5, 10, 0),   # Saturday 10am
]


def get_next_slots(now: datetime, count: int) -> list[datetime]:
    """Return the next `count` posting slots after `now`, in chronological order.

    Slots are only on Tue-Sat. Sunday/Monday return the next Tuesday slots.
    Uses a cursor that advances one week at a time to avoid double-counting.
    """
    slots: list[datetime] = []
    # Start cursor at midnight of today
    cursor = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Safety cap: never loop more than needed
    for _ in range(count * 10):
        for weekday, hour, minute in POSTING_SLOTS:
            days_ahead = (weekday - cursor.weekday()) % 7
            candidate = (cursor + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if candidate > now and candidate not in slots:
                slots.append(candidate)
            if len(slots) == count:
                return sorted(slots)
        # Advance cursor by one week to search next week's slots
        cursor += timedelta(weeks=1)

    return sorted(slots)[:count]


def schedule_uploads(reels: list[dict], upload_fn) -> None:
    """Schedule reel uploads at optimal Instagram times. Blocking process.

    Assigns each reel to the next available posting slot (greedy sequential).
    Keeps the process alive until all uploads have fired.

    Tip: run in a tmux/screen session for multi-day schedules.
    """
    tz_name = os.environ.get("PIPELINE_TIMEZONE", "")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz_name)  # validate
        except Exception:
            log.warning("Unknown timezone '%s', using local time.", tz_name)
            tz_name = ""

    now = datetime.now()
    slots = get_next_slots(now, count=len(reels))

    scheduler = BlockingScheduler(timezone=tz_name if tz_name else None)

    for reel, slot in zip(reels, slots):
        log.info(
            "Scheduled: %s at %s",
            reel["philosopher"],
            slot.strftime("%A %Y-%m-%d %H:%M"),
        )
        scheduler.add_job(
            upload_fn,
            "date",
            run_date=slot,
            args=[reel["mp4_path"], reel["caption"], reel.get("jpg_path")],
        )

    log.info("All %d jobs scheduled. Keeping process alive...", len(reels))
    log.info("Tip: run in a tmux/screen session for multi-day schedules.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user.")
