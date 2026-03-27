from pathlib import Path
import pytest
from PIL import Image
from composer import compose_reel, REEL_W, REEL_H


def make_portrait(tmp_path: Path) -> Path:
    img = Image.new("RGB", (400, 500), color=(100, 100, 100))
    p = tmp_path / "portrait.jpg"
    img.save(p)
    return p


def test_compose_reel_creates_file(tmp_path):
    out = tmp_path / "reel.jpg"
    compose_reel(make_portrait(tmp_path), "A quote.", "Nietzsche", Path("x.ttf"), out)
    assert out.exists()


def test_compose_reel_returns_path(tmp_path):
    out = tmp_path / "reel.jpg"
    result = compose_reel(make_portrait(tmp_path), "A quote.", "Camus", Path("x.ttf"), out)
    assert isinstance(result, Path)


def test_compose_reel_correct_size(tmp_path):
    out = tmp_path / "reel.jpg"
    compose_reel(make_portrait(tmp_path), "A quote.", "Camus", Path("x.ttf"), out)
    with Image.open(out) as img:
        assert img.size == (REEL_W, REEL_H)


def test_compose_reel_is_rgb(tmp_path):
    out = tmp_path / "reel.jpg"
    compose_reel(make_portrait(tmp_path), "A quote.", "Camus", Path("x.ttf"), out)
    with Image.open(out) as img:
        assert img.mode == "RGB"


def test_compose_reel_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "deep" / "reel.jpg"
    compose_reel(make_portrait(tmp_path), "Quote", "Socrates", Path("x.ttf"), out)
    assert out.exists()


def test_compose_reel_handles_long_quote(tmp_path):
    out = tmp_path / "reel.jpg"
    long_q = "This is a very long philosophical quote that should wrap across multiple lines without crashing."
    compose_reel(make_portrait(tmp_path), long_q, "Kant", Path("x.ttf"), out)
    assert out.exists()


def test_compose_reel_handles_grayscale_portrait(tmp_path):
    img = Image.new("L", (400, 500), color=128)
    p = tmp_path / "gray.jpg"
    img.save(p)
    out = tmp_path / "reel.jpg"
    compose_reel(p, "Quote", "Hegel", Path("x.ttf"), out)
    assert out.exists()
