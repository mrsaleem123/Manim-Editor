from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

LogFn = Callable[[str], None]
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".csv", ".json", ".txt", ".npy", ".npz"}


class CodeValidationError(ValueError):
    pass


@dataclass(slots=True)
class RenderResult:
    output: Path
    scene_name: str


def clean_chatgpt_code(code: str) -> str:
    lines = code.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    cleaned = [line for line in lines if line.strip().lower() not in {"`", "```", "```python", "```py"}]
    return "\n".join(cleaned).strip() + "\n"


def parse_code(code: str) -> tuple[str, ast.Module]:
    cleaned = clean_chatgpt_code(code)
    try:
        return cleaned, ast.parse(cleaned, filename="scene.py")
    except SyntaxError as exc:
        bad_line = (exc.text or "").strip()
        detail = f"Line {exc.lineno}: {exc.msg}"
        if bad_line:
            detail += f"\n{bad_line}"
        raise CodeValidationError(detail) from exc


def scene_names(code: str) -> list[str]:
    _, tree = parse_code(code)
    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)
        if any(name.endswith("Scene") for name in bases):
            found.append(node.name)
    return found


def asset_references(code: str) -> list[str]:
    _, tree = parse_code(code)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if Path(value).suffix.lower() in ASSET_SUFFIXES and value not in found:
                found.append(value)
    return found


class _AssetPathRewriter(ast.NodeTransformer):
    def __init__(self, replacements: dict[str, str]):
        self.replacements = replacements

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str) and node.value in self.replacements:
            return ast.copy_location(ast.Constant(self.replacements[node.value]), node)
        return node


def code_with_asset_paths(code: str, replacements: dict[str, str]) -> str:
    cleaned, tree = parse_code(code)
    if not replacements:
        return cleaned
    rewritten = _AssetPathRewriter(replacements).visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten) + "\n"


def _run(command: list[str], log: LogFn, cwd: Path | None = None) -> None:
    log("$ " + subprocess.list2cmdline(command))
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert process.stdout
    for line in process.stdout:
        log(line.rstrip())
    code = process.wait()
    if code:
        raise RuntimeError(f"Manim render failed with exit code {code}. See Render log for details.")


def _manim_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--studio-manim-cli"]
    found = shutil.which("manim")
    return [found] if found else [sys.executable, "-m", "manim"]


def render_code(code: str, requested_scene: str, asset_paths: dict[str, str], output: str | Path, log: LogFn = print) -> RenderResult:
    cleaned, _ = parse_code(code)
    available = scene_names(cleaned)
    scene = requested_scene.strip()
    if not scene:
        if len(available) == 1:
            scene = available[0]
        elif not available:
            raise CodeValidationError("No Manim Scene class was found in the code.")
        else:
            raise CodeValidationError("Enter a Scene class name. Available: " + ", ".join(available))
    if scene not in available:
        raise CodeValidationError(f"Scene class '{scene}' was not found. Available: {', '.join(available) or 'none'}")

    missing = [name for name in asset_references(cleaned) if name not in asset_paths and not Path(name).is_file()]
    if missing:
        raise CodeValidationError("Missing file path selection: " + ", ".join(missing))
    for selected in asset_paths.values():
        if not Path(selected).is_file():
            raise FileNotFoundError(f"Selected file no longer exists: {selected}")

    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    runtime_code = code_with_asset_paths(cleaned, asset_paths)
    with tempfile.TemporaryDirectory(prefix="mms-render-") as temp_name:
        temp = Path(temp_name)
        scene_file = temp / "scene.py"
        scene_file.write_text(runtime_code, encoding="utf-8")
        media_dir = temp / "manim-output"
        command = _manim_command() + [str(scene_file), scene, "-qh", "--format", "mp4", "--media_dir", str(media_dir), "--disable_caching"]
        _run(command, log, temp)
        candidates = sorted(media_dir.rglob("*.mp4"), key=lambda path: path.stat().st_mtime)
        if not candidates:
            raise RuntimeError("Manim completed but no MP4 file was produced.")
        shutil.copy2(candidates[-1], target)
    return RenderResult(target, scene)
