from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from .model import MediaInfo


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def executable(name: str) -> str:
    filename = name + (".exe" if os_name_is_windows() else "")
    roots = [Path(__file__).resolve().parent / "bin"]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent / "tools" / "ffmpeg")
    for root in roots:
        bundled = root / filename
        if bundled.exists():
            return str(bundled)
    found = shutil.which(name) or shutil.which(name + ".exe")
    if not found:
        raise RuntimeError(f"{name} was not found. Install FFmpeg or rebuild the offline package.")
    return found


def os_name_is_windows() -> bool:
    return sys.platform == "win32"


def _display_size(stream: dict) -> tuple[int, int, int]:
    width, height = int(stream["width"]), int(stream["height"])
    rotation = 0
    tags = stream.get("tags", {})
    if "rotate" in tags:
        rotation = int(tags["rotate"]) % 360
    for item in stream.get("side_data_list", []):
        if "rotation" in item:
            rotation = int(item["rotation"]) % 360
    if rotation in {90, 270}:
        width, height = height, width
    return width, height, rotation


def probe_media(path: str | Path) -> MediaInfo:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() in IMAGE_SUFFIXES:
        import cv2
        image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"Cannot decode image: {source}")
        height, width = image.shape[:2]
        return MediaInfo(str(source), "image", width, height, "30/1", 5.0, 150)

    command = [executable("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)]
    result = subprocess.run(command, capture_output=True, text=True, check=True, encoding="utf-8")
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The selected file has no video stream")
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    width, height, rotation = _display_size(video)
    fps = video.get("avg_frame_rate") or video.get("r_frame_rate") or "1/1"
    if fps == "0/0":
        fps = video.get("r_frame_rate", "1/1")
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
    count = video.get("nb_frames")
    frame_count = int(count) if count and str(count).isdigit() else max(1, round(duration * (eval_fraction(fps))))
    return MediaInfo(
        str(source), "video", width, height, fps, duration, frame_count,
        video.get("codec_name", ""), audio.get("codec_name", "") if audio else "", bool(audio), rotation,
    )


def eval_fraction(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def read_frame(info: MediaInfo, index: int):
    import cv2
    if info.kind == "image":
        return cv2.imread(info.path)
    capture = cv2.VideoCapture(info.path)
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, index))
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"Cannot read frame {index}")
        return frame
    finally:
        capture.release()
