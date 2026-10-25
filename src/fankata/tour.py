"""--tour: drive the real UI through each screen of the mockups and save screenshots."""

from __future__ import annotations

import os

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QTimer
from PySide6.QtGui import QGuiApplication

QUIET_ERR = "Speed at 70 °C can’t be lower than 35 % (the speed at 55 °C)."
STEPS = [
    ("01-fans", {"view": "fans", "fan": ""}, 1200),
    ("02-fans-drag", {"view": "fans", "fan": "", "drag": ["Front Intake", "loop", 2, -34, 30, 368]}, 1200),
    ("03-fan-detail", {"view": "fans", "fan": "CPU Fan"}, 1200),
    ("04-fan-menu", {"view": "fans", "fan": "CPU Fan", "fanMenu": True}, 800),
    ("05-speed-pulse", {"view": "fans", "fan": "CPU Fan", "pulse": True}, 3400),
    ("06-curves", {"view": "curves", "curve": "Balanced", "probesOpen": True, "hoverAdd": [30, 27]}, 1200),
    ("07-curve-menu", {"view": "curves", "curve": "Performance", "curveMenu": True}, 800),
    ("08-curves-probes-collapsed", {"view": "curves", "curve": "Quiet", "probesOpen": False, "hoverRemove": 1,
                                    "tableError": [3, "30", QUIET_ERR]}, 1200),
    ("09-probe-editor", {"view": "curves", "curve": "Balanced", "probesOpen": True,
                         "probe": ["mix", "sys.cpu * .9 + sys.gpu / 10"]}, 1200),
    ("10-probe-editor-error", {"view": "curves", "curve": "Balanced", "probesOpen": True,
                               "probe": ["mix", "sys.cpu * .9 + sys.gppu / 10"]}, 1200),
    ("11-service-menu", {"view": "fans", "fan": "", "appMenu": True}, 800),
    ("13-fans-wide", {"view": "fans", "fan": "", "size": [2560, 1440]}, 1800),
    ("17-troubleshoot", {"view": "fans", "fan": "", "troubleshoot": True}, 3000),
]
# Run with the service stopped (--tour-only 12-service-off): read-only mode and its banner.
EXTRA = [("12-service-off", {"view": "fans", "fan": ""}, 2500),
         # With no fan controls at all (an empty --sysfs-root, or a VM without a fan chip):
         ("16-fans-empty", {"view": "fans", "fan": ""}, 2500),
         ("19-troubleshoot-tips", {"view": "fans", "fan": "", "troubleshoot": True, "tipsOpen": True}, 3500)]


class Tour(QObject):
    def __init__(self, window, backend, out_dir: str, warmup: int = 0, only: str = ""):
        super().__init__(window)
        self.warmup = warmup
        names = [n for n in only.split(",") if n]
        self.steps = [s for s in STEPS + EXTRA if s[0] in names] if names else STEPS
        self.win = window
        self.backend = backend
        self.out = out_dir
        self.i = 0
        os.makedirs(out_dir, exist_ok=True)

    def start(self) -> None:
        self._wait = 0
        QTimer.singleShot(500, self._ready)

    def _ready(self) -> None:
        if not self.backend.connected and self._wait < 20 and self.steps is STEPS:
            self._wait += 1
            QTimer.singleShot(250, self._ready)
            return
        # real probe history for the sparklines: wait for `warmup` samples (1 per second)
        have = max((len(p["history"]) for p in self.backend.probes), default=0)
        if have < self.warmup and self._wait < 20 + 4 * (self.warmup + 10):
            self._wait += 1
            QTimer.singleShot(250, self._ready)
            return
        QTimer.singleShot(1500, self._step)

    def _step(self) -> None:
        if self.i >= len(self.steps):
            QGuiApplication.quit()
            return
        name, step, delay = self.steps[self.i]
        QMetaObject.invokeMethod(self.win, "tour", Q_ARG("QVariant", step))
        if step.get("pulse"):
            fid = next((f["id"] for f in self.backend.fans if f["name"] == step["fan"]), "")
            self.backend.startPulse(fid)
        QTimer.singleShot(delay, lambda: self._shot(name, step))

    def _shot(self, name: str, step: dict) -> None:
        img = self.win.grabWindow()
        img.save(os.path.join(self.out, f"{name}.png"))
        print("saved", name, flush=True)
        if step.get("pulse"):
            self.backend.stopPulse()
            QTimer.singleShot(600, self.backend.dismissPulseResult)
        self.i += 1
        QTimer.singleShot(700 if step.get("pulse") else 100, self._step)
