# -*- coding: utf-8 -*-
"""PyQt5 GUI for Video Subtitle Remover"""
import os
import configparser
import cv2
from threading import Thread

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QProgressBar,
    QSlider, QVBoxLayout, QHBoxLayout, QFileDialog, QTextEdit, QTabWidget,
    QFormLayout, QComboBox, QSpinBox
)

import backend.main
from backend.tools.common_tools import is_image_file


class SubtitleRemoverQT(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Video Subtitle Remover v{backend.main.config.VERSION}")
        icon_path = os.path.join(os.path.dirname(__file__), 'design', 'vsr.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.subtitle_config_file = os.path.join(os.path.dirname(__file__), 'subtitle.ini')

        self.video_path = None
        self.video_cap = None
        self.frame_count = 1
        self.frame_height = 0
        self.frame_width = 0

        self.sr = None

        self._init_ui()
        self._load_subtitle_config()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # ===== Main Tab =====
        self.main_tab = QWidget()
        main_v = QVBoxLayout(self.main_tab)

        self.video_label = QLabel(alignment=Qt.AlignCenter)
        main_v.addWidget(self.video_label)

        ctrl_layout = QHBoxLayout()
        self.open_btn = QPushButton('Open')
        self.run_btn = QPushButton('Run')
        ctrl_layout.addWidget(self.open_btn)
        ctrl_layout.addWidget(self.run_btn)
        main_v.addLayout(ctrl_layout)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(1)
        main_v.addWidget(self.slider)

        area_layout = QHBoxLayout()
        self.y_spin = QSpinBox(); self.y_spin.setPrefix('y: ')
        self.h_spin = QSpinBox(); self.h_spin.setPrefix('h: ')
        self.x_spin = QSpinBox(); self.x_spin.setPrefix('x: ')
        self.w_spin = QSpinBox(); self.w_spin.setPrefix('w: ')
        area_layout.addWidget(self.y_spin)
        area_layout.addWidget(self.h_spin)
        area_layout.addWidget(self.x_spin)
        area_layout.addWidget(self.w_spin)
        main_v.addLayout(area_layout)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        main_v.addWidget(self.output)

        self.progress = QProgressBar()
        main_v.addWidget(self.progress)

        self.tabs.addTab(self.main_tab, 'Main')

        # ===== Settings Tab =====
        self.settings_tab = QWidget()
        settings_layout = QFormLayout(self.settings_tab)
        self.algorithm_combo = QComboBox()
        for mode in backend.main.config.InpaintMode:
            self.algorithm_combo.addItem(mode.value)
        settings_layout.addRow('Algorithm', self.algorithm_combo)
        self.tabs.addTab(self.settings_tab, 'Settings')

        # connections
        self.open_btn.clicked.connect(self.open_video)
        self.run_btn.clicked.connect(self.start_remove)
        self.slider.valueChanged.connect(self.update_frame)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_progress)

    # ----- subtitle.ini helpers -----
    def _load_subtitle_config(self):
        y_p, h_p, x_p, w_p = .78, .21, .05, .9
        if not os.path.exists(self.subtitle_config_file):
            self._save_subtitle_config(y_p, h_p, x_p, w_p)
        else:
            try:
                cfg = configparser.ConfigParser()
                cfg.read(self.subtitle_config_file, encoding='utf-8')
                y_p = float(cfg['AREA']['Y'])
                h_p = float(cfg['AREA']['H'])
                x_p = float(cfg['AREA']['X'])
                w_p = float(cfg['AREA']['W'])
            except Exception:
                self._save_subtitle_config(y_p, h_p, x_p, w_p)
        self._apply_area_ratio(y_p, h_p, x_p, w_p)

    def _save_subtitle_config(self, y, h, x, w):
        with open(self.subtitle_config_file, 'w', encoding='utf-8') as f:
            f.write('[AREA]\n')
            f.write(f'Y = {y}\n')
            f.write(f'H = {h}\n')
            f.write(f'X = {x}\n')
            f.write(f'W = {w}\n')

    def _apply_area_ratio(self, y_p, h_p, x_p, w_p):
        if self.frame_height and self.frame_width:
            self.y_spin.setMaximum(self.frame_height)
            self.h_spin.setMaximum(self.frame_height)
            self.x_spin.setMaximum(self.frame_width)
            self.w_spin.setMaximum(self.frame_width)
            self.y_spin.setValue(int(self.frame_height * y_p))
            self.h_spin.setValue(int(self.frame_height * h_p))
            self.x_spin.setValue(int(self.frame_width * x_p))
            self.w_spin.setValue(int(self.frame_width * w_p))

    # ----- video helpers -----
    def show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(960, 540, Qt.KeepAspectRatio)
        self.video_label.setPixmap(pix)

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open', '',
            'Video/Image Files (*.mp4 *.flv *.wmv *.avi *.png *.jpg *.jpeg *.bmp)')
        if path:
            self.video_path = path
            if self.video_cap:
                self.video_cap.release()
            self.video_cap = cv2.VideoCapture(path)
            if self.video_cap.isOpened():
                ret, frame = self.video_cap.read()
                if ret:
                    self.frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
                    self.slider.setMaximum(max(1, self.frame_count))
                    self.frame_height = frame.shape[0]
                    self.frame_width = frame.shape[1]
                    self._apply_area_ratio(self.y_spin.value()/max(1, self.frame_height),
                                           self.h_spin.value()/max(1, self.frame_height),
                                           self.x_spin.value()/max(1, self.frame_width),
                                           self.w_spin.value()/max(1, self.frame_width))
                    self.show_frame(frame)

    def update_frame(self, value):
        if not self.video_path:
            return
        if is_image_file(self.video_path):
            img = cv2.imread(self.video_path)
            if img is not None:
                self.show_frame_with_rect(img)
        else:
            cap = cv2.VideoCapture(self.video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, value)
            ret, frame = cap.read()
            cap.release()
            if ret:
                self.show_frame_with_rect(frame)

    def show_frame_with_rect(self, frame):
        y = self.y_spin.value()
        h = self.h_spin.value()
        x = self.x_spin.value()
        w = self.w_spin.value()
        pt1 = (x, y)
        pt2 = (x + w, y + h)
        draw = cv2.rectangle(frame.copy(), pt1, pt2, (0, 255, 0), 3)
        self.show_frame(draw)

    # ----- run logic -----
    def start_remove(self):
        if not self.video_path:
            self.output.append('Please open video first')
            return
        ymin = self.y_spin.value()
        ymax = ymin + self.h_spin.value()
        xmin = self.x_spin.value()
        xmax = xmin + self.w_spin.value()
        if self.frame_height:
            y_p = ymin / self.frame_height
            h_p = self.h_spin.value() / self.frame_height
            x_p = xmin / self.frame_width
            w_p = self.w_spin.value() / self.frame_width
            self._save_subtitle_config(y_p, h_p, x_p, w_p)

        algo_text = self.algorithm_combo.currentText()
        backend.main.config.MODE = backend.main.config.InpaintMode(algo_text)

        sub_area = (ymin, ymax, xmin, xmax)
        self.sr = backend.main.SubtitleRemover(self.video_path, sub_area, True)

        def task():
            self.sr.run()

        Thread(target=task, daemon=True).start()
        self.timer.start(200)

    def refresh_progress(self):
        if not self.sr:
            return
        self.progress.setValue(self.sr.progress_total)
        if self.sr.preview_frame is not None:
            self.show_frame(self.sr.preview_frame)
        if self.sr.isFinished:
            self.timer.stop()
            self.sr = None


def main():
    import sys
    app = QApplication(sys.argv)
    win = SubtitleRemoverQT()
    win.resize(960, 720)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
