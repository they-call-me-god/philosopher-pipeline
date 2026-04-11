import subprocess
import pytest
from pathlib import Path
from PIL import Image
from composer import compose_image, compose_reel

FONT_PATH = str(Path(__file__).parent.parent / "fonts" / "PlayfairDisplay-Regular.ttf")

@pytest.fixture
def sample_photo(tmp_path):
    """Create a small test portrait photo (taller than wide)."""
    img = Image.new("RGB", (800, 1000), color=(128, 100, 80))
    path = tmp_path / "test_photo.jpg"
    img.save(path)
    return str(path)

@pytest.fixture
def composed_image(tmp_path, sample_photo):
    """Pre-composed image for reel tests."""
    out = tmp_path / "frame.jpg"
    compose_image(sample_photo, "To think is to be.", "Voltaire", str(out), FONT_PATH)
    return str(out)

@pytest.fixture
def test_audio(tmp_path):
    """Generate a 5-second silent AAC audio file via ffmpeg."""
    audio_path = str(tmp_path / "test.m4a")
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", "5", "-c:a", "aac", audio_path, "-y"
    ], check=True, capture_output=True)
    return audio_path


# ── compose_image tests ───────────────────────────────────────────────────────

def test_compose_image_creates_file(tmp_path, sample_photo):
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, "To think is to be.", "Voltaire", str(out), FONT_PATH)
    assert out.exists()
    assert out.stat().st_size > 0

def test_compose_image_correct_dimensions(tmp_path, sample_photo):
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, "Quote.", "Voltaire", str(out), FONT_PATH)
    img = Image.open(out)
    assert img.size == (1080, 1920)

def test_compose_image_is_grayscale(tmp_path, sample_photo):
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, "Quote.", "Voltaire", str(out), FONT_PATH)
    img = Image.open(out).convert("RGB")
    pixels = list(img.getdata())
    sample = pixels[::100]
    for r, g, b in sample:
        assert abs(r - g) < 10 and abs(g - b) < 10, f"Not grayscale: ({r},{g},{b})"

def test_compose_image_long_quote_doesnt_crash(tmp_path, sample_photo):
    long_quote = "This is a very long philosophical quote that goes on and on. " * 5
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, long_quote, "Philosopher", str(out), FONT_PATH)
    assert out.exists()

def test_compose_image_landscape_photo_fits(tmp_path):
    """Landscape photo (wider than tall) should still produce 1080x1920 output."""
    landscape = Image.new("RGB", (1200, 800), color=(100, 150, 200))
    photo_path = str(tmp_path / "landscape.jpg")
    landscape.save(photo_path)
    out = tmp_path / "out.jpg"
    compose_image(photo_path, "Quote.", "Thinker", str(out), FONT_PATH)
    img = Image.open(out)
    assert img.size == (1080, 1920)


# ── compose_reel tests ────────────────────────────────────────────────────────

def test_compose_reel_creates_mp4(tmp_path, composed_image, test_audio):
    out = str(tmp_path / "reel.mp4")
    compose_reel(composed_image, test_audio, out, duration=5)
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000

def test_compose_reel_produces_valid_container(tmp_path, composed_image, test_audio):
    """Verify ffprobe can read the output as a valid MP4."""
    out = str(tmp_path / "reel.mp4")
    compose_reel(composed_image, test_audio, out, duration=5)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name",
         "-of", "default=noprint_wrappers=1:nokey=1", out],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "mp4" in result.stdout.lower() or "mov" in result.stdout.lower()


def test_compose_image_text_centered(tmp_path, sample_photo):
    """Verify bright pixels (white text) exist near the vertical center of the image."""
    out = tmp_path / "centered.jpg"
    compose_image(sample_photo, "Quote.", "Voltaire", str(out), FONT_PATH)
    img = Image.open(out).convert("L")  # grayscale
    w, h = img.size
    # Sample pixels in the center band (40-60% vertically)
    center_top = int(h * 0.40)
    center_bot = int(h * 0.60)
    center_pixels = [img.getpixel((w // 2, y)) for y in range(center_top, center_bot, 5)]
    # At least some pixels should be bright (white text)
    assert max(center_pixels) > 200, "No bright pixels found near vertical center — text may be misplaced"
