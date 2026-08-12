from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

from .media import executable
from .model import StudioProject


LogFn = Callable[[str], None]


@dataclass(slots=True)
class RenderResult:
    overlay: Path
    output: Path


def _run(command: list[str], log: LogFn, cwd: Path | None = None) -> None:
    log("$ " + subprocess.list2cmdline(command))
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert process.stdout
    for line in process.stdout:
        log(line.rstrip())
    code = process.wait()
    if code:
        raise RuntimeError(f"Command failed with exit code {code}")


def _manim_command() -> list[str]:
    bundled = Path(sys.executable).with_name("manim.exe")
    if bundled.exists():
        return [str(bundled)]
    found = shutil.which("manim")
    return [found] if found else [sys.executable, "-m", "manim"]


def render_project(project: StudioProject, output: str | Path, log: LogFn = print) -> RenderResult:
    if not project.media:
        raise ValueError("Import media before rendering")
    info = project.media
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mms-render-") as temp_name:
        temp = Path(temp_name)
        scene_file = temp / "scene.py"
        scene_file.write_text(project.scene_code, encoding="utf-8")
        if project.tracking_path:
            tracking_source = Path(project.tracking_path)
            if tracking_source.is_file():
                shutil.copy2(tracking_source, temp / "tracking.json")
                helper = tracking_source.parent / "studio_tracking.py"
                if helper.is_file():
                    shutil.copy2(helper, temp / "studio_tracking.py")
        media_dir = temp / "manim-output"
        command = _manim_command() + [
            str(scene_file), project.scene_name, "--media_dir", str(media_dir),
            "--format", "mov", "--transparent", "--fps", f"{info.fps:.8f}",
            "-r", f"{info.width},{info.height}", "--disable_caching",
        ]
        _run(command, log, temp)
        candidates = sorted(media_dir.rglob("*.mov"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError("Manim completed but no transparent MOV was produced")
        overlay = candidates[-1]
        if info.kind == "video":
            filter_graph = "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]"
            ffmpeg = [executable("ffmpeg"), "-y", "-i", info.path, "-i", str(overlay),
                      "-filter_complex", filter_graph, "-map", "[v]"]
            if info.has_audio:
                ffmpeg += ["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"]
            ffmpeg += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]
        else:
            duration = max(0.1, info.duration or 5.0)
            ffmpeg = [executable("ffmpeg"), "-y", "-loop", "1", "-i", info.path, "-i", str(overlay),
                      "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]", "-map", "[v]",
                      "-t", str(duration), "-r", f"{info.fps:.8f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)]
        _run(ffmpeg, log, temp)
        saved_overlay = target.with_name(target.stem + "-overlay.mov")
        shutil.copy2(overlay, saved_overlay)
    return RenderResult(saved_overlay, target)
