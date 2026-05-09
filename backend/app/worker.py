import signal
import time

from app.config import get_settings
from app.db import get_conn, init_db
from app.services.import_runner import ImportRunner

running = True


def _stop(*_args):
    global running
    running = False


def main() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    settings = get_settings()
    settings.import_dir.mkdir(parents=True, exist_ok=True)
    settings.attachment_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    runner = ImportRunner(settings)
    with get_conn() as conn:
        runner.reset_interrupted_jobs(conn)

    while running:
        with get_conn() as conn:
            job = runner.claim_next_job(conn)
            if job:
                runner.run_job(conn, job)
                continue
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()

