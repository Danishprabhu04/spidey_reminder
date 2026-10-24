"""Compact stats strip for the mission panel: streak, counts, 7-day bars."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from hanging_reminder.tasks.stats import WeekSummary

TEXT = QColor(220, 220, 220)
MUTED = QColor(140, 146, 158)
BAR = QColor(220, 50, 50)
BAR_TODAY = QColor(230, 130, 30)
BAR_EMPTY = QColor(255, 255, 255, 25)
HEIGHT = 112


def _minutes(value: float) -> str:
    value = int(round(value))
    return f"{value // 60}h {value % 60:02d}m" if value >= 60 else f"{value}m"


class StatsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary: WeekSummary | None = None
        self.setFixedHeight(HEIGHT)

    def set_summary(self, summary: WeekSummary) -> None:
        self._summary = summary
        self.update()

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(260, HEIGHT)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        s = self._summary
        if s is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = float(self.width())

        # Headline numbers
        tiles = (
            (f"\U0001F525 {s.streak}", "day streak"),
            (str(s.done_today), "done today"),
            (str(s.done_week), "this week"),
            (_minutes(s.focus_today_min), "focus today"),
        )
        tile_w = w / len(tiles)
        big, small = QFont("Sans", 12), QFont("Sans", 8)
        big.setBold(True)
        for i, (value, label) in enumerate(tiles):
            x = i * tile_w
            p.setFont(big)
            p.setPen(QPen(TEXT))
            p.drawText(QRectF(x, 0, tile_w, 22), int(Qt.AlignmentFlag.AlignCenter), value)
            p.setFont(small)
            p.setPen(QPen(MUTED))
            p.drawText(QRectF(x, 20, tile_w, 14), int(Qt.AlignmentFlag.AlignCenter), label)

        # 7-day bars
        top, bottom = 44.0, HEIGHT - 16.0
        peak = max(1, max(s.daily_done))
        slot = w / 7
        bar_w = slot * 0.5
        p.setFont(small)
        for i, (day, count) in enumerate(zip(s.days, s.daily_done)):
            cx = slot * i + slot / 2
            full = bottom - top
            h = full * count / peak
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(BAR_EMPTY)
            p.drawRoundedRect(QRectF(cx - bar_w / 2, top, bar_w, full), 3, 3)
            if count:
                p.setBrush(BAR_TODAY if i == 6 else BAR)
                p.drawRoundedRect(QRectF(cx - bar_w / 2, bottom - h, bar_w, h), 3, 3)
            p.setPen(QPen(TEXT if i == 6 else MUTED))
            p.drawText(QRectF(cx - slot / 2, bottom + 1, slot, 14),
                       int(Qt.AlignmentFlag.AlignCenter), day.strftime("%a")[0])
        p.end()
