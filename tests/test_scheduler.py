from unittest.mock import MagicMock, patch


def test_scheduler_adds_job():
    with patch("scheduler.BlockingScheduler") as Mock:
        Mock.return_value.start.side_effect = KeyboardInterrupt
        from scheduler import start_scheduler
        start_scheduler(9, 0)
        assert Mock.return_value.add_job.called


def test_scheduler_uses_cron_trigger():
    with patch("scheduler.BlockingScheduler") as Mock:
        Mock.return_value.start.side_effect = KeyboardInterrupt
        from scheduler import start_scheduler
        start_scheduler(9, 0)
        kwargs = Mock.return_value.add_job.call_args[1]
        assert kwargs["trigger"] == "cron"


def test_scheduler_passes_hour_minute():
    with patch("scheduler.BlockingScheduler") as Mock:
        Mock.return_value.start.side_effect = KeyboardInterrupt
        from scheduler import start_scheduler
        start_scheduler(14, 30)
        kwargs = Mock.return_value.add_job.call_args[1]
        assert kwargs["hour"] == 14 and kwargs["minute"] == 30


def test_scheduler_handles_keyboard_interrupt():
    with patch("scheduler.BlockingScheduler") as Mock:
        Mock.return_value.start.side_effect = KeyboardInterrupt
        from scheduler import start_scheduler
        start_scheduler(9, 0)  # should not raise


def test_scheduler_handles_system_exit():
    with patch("scheduler.BlockingScheduler") as Mock:
        Mock.return_value.start.side_effect = SystemExit
        from scheduler import start_scheduler
        start_scheduler(9, 0)  # should not raise
