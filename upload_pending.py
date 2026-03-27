"""Upload any MP4 files in output/ that haven't been posted yet."""
import logging
from pathlib import Path

from dotenv import load_dotenv

from uploader import upload_reel

load_dotenv()
log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
POSTED_LOG = Path(__file__).parent / "posted.txt"


def get_posted() -> set[str]:
    if POSTED_LOG.exists():
        return set(POSTED_LOG.read_text().splitlines())
    return set()


def mark_posted(video_name: str) -> None:
    with POSTED_LOG.open("a") as f:
        f.write(video_name + "\n")


def main() -> None:
    posted = get_posted()
    pending = [v for v in sorted(OUTPUT_DIR.glob("*.mp4")) if v.name not in posted]

    if not pending:
        print("No pending videos to upload.")
        return

    for video_path in pending:
        philosopher = video_path.stem.replace("_reel", "").replace("_", " ").title()
        caption = f'Philosophy for the soul.\n— {philosopher}\n\n#philosophy #quotes #wisdom'
        try:
            upload_reel(video_path=video_path, caption=caption)
            mark_posted(video_path.name)
            print(f"✓ Uploaded {video_path.name}")
        except Exception as e:
            print(f"✗ Failed {video_path.name}: {e}")


if __name__ == "__main__":
    main()
