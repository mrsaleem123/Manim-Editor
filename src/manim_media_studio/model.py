from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction
import json
from pathlib import Path


@dataclass(slots=True)
class MediaInfo:
    path: str
    kind: str
    width: int
    height: int
    fps_fraction: str = "1/1"
    duration: float = 0.0
    frame_count: int = 1
    video_codec: str = ""
    audio_codec: str = ""
    has_audio: bool = False
    rotation: int = 0

    @property
    def fps(self) -> float:
        return float(Fraction(self.fps_fraction))


DEFAULT_SCENE = '''from manim import *

class OverlayScene(Scene):
    def construct(self):
        title = Text("Your animation", font_size=64, color=YELLOW)
        title.set_stroke(BLACK, width=2, background=True)
        self.play(Write(title))
        self.wait(1)
        self.play(title.animate.to_edge(UP))
'''


@dataclass(slots=True)
class StudioProject:
    media: MediaInfo | None = None
    scene_name: str = "OverlayScene"
    scene_code: str = DEFAULT_SCENE
    output_path: str = ""
    tracking_path: str = ""
    project_path: str = field(default="", repr=False)

    def save(self, path: str | Path) -> None:
        target = Path(path).resolve()
        payload = asdict(self)
        payload.pop("project_path", None)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.project_path = str(target)

    @classmethod
    def load(cls, path: str | Path) -> "StudioProject":
        target = Path(path).resolve()
        raw = json.loads(target.read_text(encoding="utf-8"))
        media = MediaInfo(**raw["media"]) if raw.get("media") else None
        raw["media"] = media
        project = cls(**raw)
        project.project_path = str(target)
        return project
