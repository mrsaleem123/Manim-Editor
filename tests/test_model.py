from pathlib import Path

from manim_media_studio.media import eval_fraction
from manim_media_studio.model import MediaInfo, StudioProject
from manim_media_studio.render import asset_references, clean_chatgpt_code, code_with_asset_paths, scene_names


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


def test_chatgpt_markdown_is_cleaned():
    code = "```python\nfrom manim import *\nclass Demo(Scene):\n    pass\n`\n```"
    cleaned = clean_chatgpt_code(code)
    assert "`" not in cleaned
    assert scene_names(cleaned) == ["Demo"]


def test_assets_are_discovered_and_rewritten():
    code = 'from manim import *\nclass Demo(Scene):\n def construct(self):\n  self.add(ImageMobject("earth.png"))\n'
    assert asset_references(code) == ["earth.png"]
    rewritten = code_with_asset_paths(code, {"earth.png": "C:/Media/earth.png"})
    assert "C:/Media/earth.png" in rewritten
