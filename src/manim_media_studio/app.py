from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import traceback

from platformdirs import user_cache_path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QStatusBar, QVBoxLayout, QWidget

from .model import DEFAULT_SCENE
from .render import CodeValidationError, asset_references, clean_chatgpt_code, render_code, scene_names


def configure_bundled_tools() -> None:
    if not getattr(sys, "frozen", False):
        return
    root = Path(sys.executable).resolve().parent / "tools"
    candidates = [root / "ffmpeg", root / "miktex" / "bin" / "x64", root / "miktex" / "bin"]
    existing = [str(path) for path in candidates if path.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing + [os.environ.get("PATH", "")])


class WorkerSignals(QObject):
    log = Signal(str)
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.done.emit(self.fn(self.signals.log.emit))
        except Exception:
            self.signals.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        self.latest_output: Path | None = None
        self.render_worker: Worker | None = None
        self.setWindowTitle("Manim Studio 1.1.0")
        self.resize(1120, 760)

        root = QWidget()
        outer = QVBoxLayout(root)
        heading = QLabel("Manim Studio")
        heading.setStyleSheet("font-size:24px;font-weight:600")
        subtitle = QLabel("Paste ChatGPT-generated Manim code. Missing image/video paths will be requested automatically.")
        subtitle.setStyleSheet("color:#666")
        outer.addWidget(heading)
        outer.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.render_button = QPushButton("Render")
        self.download_button = QPushButton("Download Video")
        self.reset_button = QPushButton("Reset")
        self.download_button.setEnabled(False)
        self.render_button.clicked.connect(self.render)
        self.download_button.clicked.connect(self.download_video)
        self.reset_button.clicked.connect(self.reset)
        for button in (self.render_button, self.download_button, self.reset_button):
            button.setMinimumHeight(42)
            toolbar.addWidget(button)
        outer.addLayout(toolbar)

        outer.addWidget(QLabel("Scene class (leave blank to auto-detect)"))
        self.scene_name = QLineEdit()
        outer.addWidget(self.scene_name)

        split = QSplitter()
        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(QLabel("Manim code"))
        self.editor = QPlainTextEdit(DEFAULT_SCENE)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setStyleSheet("font-family:Consolas,monospace;font-size:13px")
        editor_layout.addWidget(self.editor)

        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Render log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:Consolas,monospace;font-size:12px;background:#111;color:#ddd")
        log_layout.addWidget(self.log)
        split.addWidget(editor_panel)
        split.addWidget(log_panel)
        split.setSizes([700, 420])
        outer.addWidget(split, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready — paste code and click Render")

    def _set_busy(self, busy: bool) -> None:
        self.render_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.download_button.setEnabled(not busy and self.latest_output is not None)

    def _select_assets(self, code: str) -> dict[str, str] | None:
        selected: dict[str, str] = {}
        for reference in asset_references(code):
            if Path(reference).is_file():
                continue
            path, _ = QFileDialog.getOpenFileName(self, f"Select file for: {reference}", "", "Supported files (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg *.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.wav *.csv *.json *.txt *.npy *.npz);;All files (*.*)")
            if not path:
                self.statusBar().showMessage(f"Render cancelled — file not selected: {reference}")
                return None
            selected[reference] = path
        return selected

    def render(self) -> None:
        raw_code = self.editor.toPlainText()
        try:
            cleaned = clean_chatgpt_code(raw_code)
            available = scene_names(cleaned)
            requested = self.scene_name.text().strip()
            if not requested and len(available) == 1:
                requested = available[0]
                self.scene_name.setText(requested)
            assets = self._select_assets(cleaned)
            if assets is None:
                return
        except CodeValidationError as exc:
            QMessageBox.critical(self, "Code error", str(exc))
            self.statusBar().showMessage("Code validation failed")
            return

        if cleaned != raw_code:
            self.editor.setPlainText(cleaned)
        output = user_cache_path("Manim Studio", appauthor=False) / "renders" / "latest.mp4"
        self.log.clear()
        self.log.appendPlainText("Code validated. Starting Manim render…")
        self.latest_output = None
        self._set_busy(True)
        self.statusBar().showMessage("Rendering…")
        worker = Worker(lambda logger: render_code(cleaned, requested, assets, output, logger))
        self.render_worker = worker
        worker.signals.log.connect(self.log.appendPlainText)
        worker.signals.done.connect(self._render_done)
        worker.signals.failed.connect(self._render_failed)
        self.pool.start(worker)

    def _render_done(self, result) -> None:
        self.latest_output = result.output
        self.scene_name.setText(result.scene_name)
        self._set_busy(False)
        self.log.appendPlainText(f"\nRender complete: {result.output}")
        self.statusBar().showMessage("Render complete — click Download Video")
        QMessageBox.information(self, "Render complete", "Video is ready. Click Download Video to save it.")

    def _render_failed(self, detail: str) -> None:
        self._set_busy(False)
        self.log.appendPlainText("\n" + detail)
        message = detail.strip().splitlines()[-1] if detail.strip() else "Unknown render error"
        self.statusBar().showMessage("Render failed — see Render log")
        QMessageBox.critical(self, "Render failed", message)

    def download_video(self) -> None:
        if not self.latest_output or not self.latest_output.is_file():
            QMessageBox.information(self, "No video", "Render a video first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Download rendered video", "manim-animation.mp4", "MP4 video (*.mp4)")
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".mp4":
            target = target.with_suffix(".mp4")
        shutil.copy2(self.latest_output, target)
        self.statusBar().showMessage(f"Video saved: {target}")
        QMessageBox.information(self, "Download complete", f"Video saved to:\n{target}")

    def reset(self) -> None:
        self.editor.setPlainText(DEFAULT_SCENE)
        self.scene_name.clear()
        self.log.clear()
        self.latest_output = None
        self._set_busy(False)
        self.statusBar().showMessage("Reset complete")


def main() -> int:
    configure_bundled_tools()
    app = QApplication(sys.argv)
    app.setApplicationName("Manim Studio")
    window = MainWindow()
    window.show()
    return app.exec()
