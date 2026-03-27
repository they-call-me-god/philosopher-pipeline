"""Test upload — place a test.mp4 in output/ and run this to verify credentials."""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TEST_VIDEO = Path(__file__).parent / "output" / "test_reel.mp4"


def main() -> None:
    if not TEST_VIDEO.exists():
        print(f"Place a short test MP4 at: {TEST_VIDEO}")
        return
    from uploader import upload_reel
    media_id = upload_reel(video_path=TEST_VIDEO, caption="Test 🖤 #test")
    print(f"✓ Upload successful. Media ID: {media_id}")


if __name__ == "__main__":
    main()
