from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import cv2

from .model import MediaInfo


MANIM_HELPER = '''from __future__ import annotations
import json
from pathlib import Path
from manim import config

class StudioTracking:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.frames = self.data["frames"]
        self.width, self.height = self.data["size"]

    def frame(self, index):
        return self.frames[max(0, min(int(index), len(self.frames) - 1))]

    def point(self, index):
        item = self.frame(index)
        if item.get("lost"):
            return None
        x, y = item["center"]
        # Source pixels (top-left origin) to Manim units (center origin).
        return ((x / self.width - 0.5) * config.frame_width,
                (0.5 - y / self.height) * config.frame_height,
                0)
'''


def _tracker():
    maker = getattr(cv2, "TrackerCSRT_create", None)
    if maker:
        return maker()
    legacy = getattr(cv2, "legacy", None)
    if legacy and hasattr(legacy, "TrackerCSRT_create"):
        return legacy.TrackerCSRT_create()
    raise RuntimeError("OpenCV CSRT tracker is unavailable; install opencv-contrib-python")


def track(info: MediaInfo, roi: tuple[int, int, int, int], output: str | Path, progress: Callable[[int, int], None] | None = None) -> Path:
    if info.kind != "video":
        raise ValueError("Tracking requires a video")
    capture = cv2.VideoCapture(info.path)
    ok, frame = capture.read()
    if not ok:
        capture.release()
        raise RuntimeError("Cannot read the first frame")
    tracker = _tracker()
    tracker.init(frame, roi)
    points = []
    index = 0
    try:
        while ok:
            success, box = tracker.update(frame)
            if success:
                x, y, w, h = [float(v) for v in box]
                points.append({"frame": index, "time": index / info.fps, "x": x, "y": y, "width": w, "height": h, "center": [x + w / 2, y + h / 2]})
            else:
                points.append({"frame": index, "time": index / info.fps, "lost": True})
            if progress and index % 5 == 0:
                progress(index, info.frame_count)
            ok, frame = capture.read()
            index += 1
    finally:
        capture.release()
    target = Path(output).resolve()
    target.write_text(json.dumps({"source": info.path, "fps": info.fps_fraction, "size": [info.width, info.height], "frames": points}, indent=2), encoding="utf-8")
    (target.parent / "studio_tracking.py").write_text(MANIM_HELPER, encoding="utf-8")
    return target
