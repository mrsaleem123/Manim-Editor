from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback
import os

import cv2
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSlider, QSpinBox, QSplitter, QStatusBar, QVBoxLayout, QWidget)

from .media import probe_media, read_frame
from .model import StudioProject
from .render import render_project
from .tracking import track


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
        super().__init__(); self.fn = fn; self.signals = WorkerSignals()
    @Slot()
    def run(self):
        try: self.signals.done.emit(self.fn(self.signals.log.emit))
        except Exception: self.signals.failed.emit(traceback.format_exc())


class RoiDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent); self.setWindowTitle("Tracking rectangle on first frame")
        form = QFormLayout(self); self.boxes = []
        for label, maximum in (("X", width - 1), ("Y", height - 1), ("Width", width), ("Height", height)):
            box = QSpinBox(); box.setRange(0 if len(self.boxes) < 2 else 1, max(1, maximum)); box.setValue(max(1, maximum // (4 if len(self.boxes) < 2 else 3)))
            form.addRow(label, box); self.boxes.append(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)
    def roi(self): return tuple(box.value() for box in self.boxes)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.project = StudioProject(); self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("Manim Media Studio 1.0"); self.resize(1280, 800)
        root = QWidget(); outer = QVBoxLayout(root); toolbar = QHBoxLayout()
        for text, callback in (("Import Media", self.import_media), ("Open Project", self.open_project), ("Save Project", self.save_project), ("Track Object", self.track_object), ("Render Final MP4", self.render)):
            button = QPushButton(text); button.clicked.connect(callback); toolbar.addWidget(button)
        outer.addLayout(toolbar)
        split = QSplitter(); left = QWidget(); left_layout = QVBoxLayout(left)
        self.preview = QLabel("Import an image or video"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumSize(480, 270); self.preview.setStyleSheet("background:#111;color:#aaa")
        self.slider = QSlider(Qt.Horizontal); self.slider.setEnabled(False); self.slider.valueChanged.connect(self.show_frame)
        self.metadata = QPlainTextEdit(); self.metadata.setReadOnly(True); self.metadata.setMaximumHeight(190)
        left_layout.addWidget(self.preview, 1); left_layout.addWidget(self.slider); left_layout.addWidget(self.metadata)
        right = QWidget(); right_layout = QVBoxLayout(right)
        self.scene_name = QLineEdit(self.project.scene_name); self.editor = QPlainTextEdit(self.project.scene_code); self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(190)
        right_layout.addWidget(QLabel("Scene class")); right_layout.addWidget(self.scene_name); right_layout.addWidget(QLabel("Manim code")); right_layout.addWidget(self.editor, 1); right_layout.addWidget(QLabel("Render log")); right_layout.addWidget(self.log)
        split.addWidget(left); split.addWidget(right); split.setSizes([560, 720]); outer.addWidget(split, 1)
        self.setCentralWidget(root); self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Ready")

    def sync(self): self.project.scene_name = self.scene_name.text().strip(); self.project.scene_code = self.editor.toPlainText()
    def fail(self, detail): self.statusBar().showMessage("Failed"); self.log.appendPlainText(detail); QMessageBox.critical(self, "Operation failed", detail.splitlines()[-1])
    def import_media(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import media", "", "Media (*.mp4 *.mov *.mkv *.avi *.webm *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if not path: return
        try:
            self.project.media = probe_media(path); self.refresh_media()
        except Exception as exc: self.fail(str(exc))
    def refresh_media(self):
        info = self.project.media
        if not info: return
        self.metadata.setPlainText(json.dumps({"path": info.path, "type": info.kind, "resolution": f"{info.width} x {info.height}", "fps": info.fps_fraction, "fps_decimal": info.fps, "duration": info.duration, "frames": info.frame_count, "video_codec": info.video_codec, "audio_codec": info.audio_codec, "rotation": info.rotation}, indent=2))
        self.slider.setEnabled(info.kind == "video"); self.slider.setRange(0, max(0, info.frame_count - 1)); self.show_frame(0); self.statusBar().showMessage("Media loaded")
    def show_frame(self, index):
        if not self.project.media: return
        try:
            frame = read_frame(self.project.media, index); rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); h, w, channels = rgb.shape
            image = QImage(rgb.data, w, h, channels * w, QImage.Format_RGB888).copy(); pixmap = QPixmap.fromImage(image).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation); self.preview.setPixmap(pixmap)
        except Exception as exc: self.statusBar().showMessage(str(exc))
    def save_project(self):
        self.sync(); path = self.project.project_path
        if not path: path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.mms.json", "Studio Project (*.mms.json)")
        if path: self.project.save(path); self.statusBar().showMessage(f"Saved {path}")
    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Studio Project (*.mms.json)")
        if not path: return
        try:
            self.project = StudioProject.load(path); self.scene_name.setText(self.project.scene_name); self.editor.setPlainText(self.project.scene_code); self.refresh_media()
        except Exception as exc: self.fail(str(exc))
    def track_object(self):
        info = self.project.media
        if not info or info.kind != "video": QMessageBox.information(self, "Tracking", "Import a video first."); return
        dialog = RoiDialog(info.width, info.height, self)
        if dialog.exec() != QDialog.Accepted: return
        path, _ = QFileDialog.getSaveFileName(self, "Save tracking data", "tracking.json", "JSON (*.json)")
        if not path: return
        roi = dialog.roi(); self.statusBar().showMessage("Tracking…")
        worker = Worker(lambda log: track(info, roi, path)); worker.signals.done.connect(lambda result: self.tracking_done(str(result))); worker.signals.failed.connect(self.fail); self.pool.start(worker)
    def tracking_done(self, path): self.project.tracking_path = path; self.statusBar().showMessage(f"Tracking saved: {path}")
    def render(self):
        if not self.project.media: QMessageBox.information(self, "Render", "Import media first."); return
        self.sync(); path, _ = QFileDialog.getSaveFileName(self, "Render final video", "output.mp4", "MP4 video (*.mp4)")
        if not path: return
        self.log.clear(); self.statusBar().showMessage("Rendering…")
        worker = Worker(lambda logger: render_project(self.project, path, logger)); worker.signals.log.connect(self.log.appendPlainText); worker.signals.done.connect(lambda result: self.statusBar().showMessage(f"Rendered {result.output}")); worker.signals.failed.connect(self.fail); self.pool.start(worker)


def main() -> int:
    configure_bundled_tools(); app = QApplication(sys.argv); app.setApplicationName("Manim Media Studio"); window = MainWindow(); window.show(); return app.exec()
