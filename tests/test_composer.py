import subprocess
import pytest
from pathlib import Path
from PIL import Image
from composer import compose_image, compose_reel, compose_frame, compose_slideshow

FONT_PATH = str(Path(__file__).parent.parent / "fonts" / "PlayfairDisplay-Regular.ttf")


@pytest.fixture
def sample_photo(tmp_path):
    """Create a small test color photo (taller than wide)."""
    img = Image.new("RGB", (800, 1000), color=(180, 90, 60))
    path = tmp_path / "test_photo.jpg"
    img.save(path)
    return str(path)


@pytest.fixture
def sample_painting(tmp_path):
    """Create a wider color test image (Renaissance paintings often landscape)."""
    img = Image.new("RGB", (1200, 900), color=(120, 80, 50))
    path = tmp_path / "painting.jpg"
    img.save(path)
    return str(path)


@pytest.fixture
def composed_image(tmp_path, sample_photo):
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


# compose_image / compose_frame tests

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


def test_compose_image_long_quote_doesnt_crash(tmp_path, sample_photo):
    long_quote = "This is a very long philosophical quote that goes on and on. " * 5
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, long_quote, "Philosopher", str(out), FONT_PATH)
    assert out.exists()


def test_compose_image_landscape_photo_fits(tmp_path):
    landscape = Image.new("RGB", (1200, 800), color=(100, 150, 200))
    photo_path = str(tmp_path / "landscape.jpg")
    landscape.save(photo_path)
    out = tmp_path / "out.jpg"
    compose_image(photo_path, "Quote.", "Thinker", str(out), FONT_PATH)
    img = Image.open(out)
    assert img.size == (1080, 1920)


def test_compose_image_preserves_color(tmp_path, sample_photo):
    """After dropping the B&W filter, output should NOT be grayscale."""
    out = tmp_path / "out.jpg"
    compose_image(sample_photo, "Quote.", "Voltaire", str(out), FONT_PATH)
    img = Image.open(out).convert("RGB")
    pixels = list(img.getdata())
    # Sample pixels in the upper region (above text band) where source color shows
    w, h = img.size
    sample = [img.getpixel((w // 2, y)) for y in range(50, 400, 10)]
    has_color = any(abs(r - g) > 12 or abs(g - b) > 12 for r, g, b in sample)
    assert has_color, "compose_image output appears grayscale, expected color"


def test_compose_image_text_centered(tmp_path, sample_photo):
    """White text should be visible near vertical center."""
    out = tmp_path / "centered.jpg"
    compose_image(sample_photo, "Quote.", "Voltaire", str(out), FONT_PATH)
    img = Image.open(out).convert("L")
    w, h = img.size
    center_top = int(h * 0.40)
    center_bot = int(h * 0.60)
    center_pixels = [img.getpixel((w // 2, y)) for y in range(center_top, center_bot, 5)]
    assert max(center_pixels) > 200, "No bright pixels near vertical center, text may be misplaced"


def test_compose_frame_includes_watermark(tmp_path, sample_painting):
    """Frame should render bright pixels near the bottom (watermark zone)."""
    out = tmp_path / "wm.jpg"
    compose_frame(sample_painting, "Quote.", "Author", str(out), FONT_PATH)
    img = Image.open(out).convert("L")
    w, h = img.size
    # Watermark sits ~90px above bottom edge
    wm_band_top = h - 160
    wm_band_bot = h - 60
    wm_pixels = [img.getpixel((x, y))
                 for y in range(wm_band_top, wm_band_bot, 8)
                 for x in range(0, w, 30)]
    # Watermark is intentionally semi-transparent (alpha 130 over arbitrary
    # backgrounds), so post-composite pixel intensity tops out around 165.
    assert max(wm_pixels) > 150, "No bright pixels in watermark band"


# compose_reel tests (legacy single-image path)

def test_compose_reel_creates_mp4(tmp_path, composed_image, test_audio):
    out = str(tmp_path / "reel.mp4")
    compose_reel(composed_image, test_audio, out, duration=5)
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000


def test_compose_reel_produces_valid_container(tmp_path, composed_image, test_audio):
    out = str(tmp_path / "reel.mp4")
    compose_reel(composed_image, test_audio, out, duration=5)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name",
         "-of", "default=noprint_wrappers=1:nokey=1", out],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "mp4" in result.stdout.lower() or "mov" in result.stdout.lower()


# compose_slideshow tests

def test_compose_slideshow_creates_mp4(tmp_path, sample_photo, sample_painting, test_audio):
    out = str(tmp_path / "slide.mp4")
    compose_slideshow(
        [sample_photo, sample_painting, sample_photo, sample_painting],
        "Quote.", "Author",
        test_audio, out, FONT_PATH,
        frame_duration=0.5, reel_duration=2,
    )
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000


def test_compose_slideshow_loops_short_input(tmp_path, sample_painting, test_audio):
    """When fewer images are supplied than frames needed, they should loop."""
    out = str(tmp_path / "loop.mp4")
    compose_slideshow(
        [sample_painting], "Quote.", "Author",
        test_audio, out, FONT_PATH,
        frame_duration=0.4, reel_duration=2,
    )
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000


def test_compose_slideshow_empty_raises(tmp_path, test_audio):
    out = str(tmp_path / "x.mp4")
    with pytest.raises(ValueError):
        compose_slideshow([], "Q", "A", test_audio, out, FONT_PATH)
