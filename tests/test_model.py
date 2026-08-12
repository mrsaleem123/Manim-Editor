from pathlib import Path

from manim_media_studio.media import eval_fraction
from manim_media_studio.model import MediaInfo, StudioProject


def test_fractional_fps():
    assert abs(eval_fraction("30000/1001") - 29.97002997) < 1e-8


def test_project_roundtrip(tmp_path: Path):
    target = tmp_path / "demo.mms.json"
    project = StudioProject(media=MediaInfo("clip.mp4", "video", 1920, 1080, "30000/1001", 10, 300, "h264", "aac", True))
    project.save(target)
    loaded = StudioProject.load(target)
    assert loaded.media is not None
    assert loaded.media.fps_fraction == "30000/1001"
    assert loaded.media.has_audio is True
