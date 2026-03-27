"""APScheduler daemon — runs pipeline daily at a configured time."""
import argparse
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from pipeline import run_pipeline

log = logging.getLogger(__name__)


def start_scheduler(hour: int = 9, minute: int = 0) -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: run_pipeline(single=True),
        trigger="cron",
        hour=hour,
        minute=minute,
        id="philosopher_pipeline",
    )
    log.info("Scheduler running. Posts daily at %02d:%02d local time.", hour, minute)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Philosopher Pipeline Scheduler")
    parser.add_argument("--hour", type=int, default=9, help="Hour to post (24h, local time)")
    parser.add_argument("--minute", type=int, default=0, help="Minute to post")
    parser.add_argument("--status", action="store_true", help="Print status and exit")
    args = parser.parse_args()

    if args.status:
        print("Scheduler is not currently running. Start with: python scheduler.py")
        return

    start_scheduler(hour=args.hour, minute=args.minute)


if __name__ == "__main__":
    main()
