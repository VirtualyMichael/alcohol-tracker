from __future__ import annotations

import json
import csv
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from alcohol_tracker.core.calculations import (
    Ingestion,
    effect_series,
    estimated_clear_time,
    estimate_active_standard_drinks,
    estimate_bac,
    group_into_sessions,
    peak_value,
    tolerance_series,
)
from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.core.paths import default_db_path
from alcohol_tracker.core.settings import load_estimate_settings, save_estimate_settings
from alcohol_tracker.ui.dialogs import IngestionDialog, PresetDialog, SettingsDialog


class TimelineGraph(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.points: list[tuple[datetime, float]] = []
        self.markers: list[datetime] = []
        self.empty_message = "No ingestions logged for this view"
        self.hover_pos: QPointF | None = None
        self.bac_converter = None
        self.setMouseTracking(True)
        self.setMinimumHeight(265)

    def set_bac_converter(self, converter) -> None:
        self.bac_converter = converter

    def mouseMoveEvent(self, event) -> None:
        self.hover_pos = event.position()
        self.update()

    def leaveEvent(self, event) -> None:
        self.hover_pos = None
        self.update()

    def set_points(self, points: list[tuple[datetime, float]], markers: list[datetime] | None = None) -> None:
        self.points = points
        self.markers = markers or []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#343840"), 1))
        painter.setBrush(QBrush(QColor("#15171a")))
        painter.drawRoundedRect(rect, 8, 8)

        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.setPen(QColor("#ececef"))
        painter.drawText(rect.adjusted(16, 14, -16, -14), Qt.AlignTop | Qt.AlignLeft, self.title)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#9da3ad"))
        painter.drawText(rect.adjusted(16, 40, -16, -14), Qt.AlignTop | Qt.AlignLeft, self.subtitle)

        graph = rect.adjusted(30, 78, -30, -42)
        painter.setPen(QPen(QColor("#252930"), 1))
        for i in range(4):
            y = graph.top() + graph.height() * i / 3
            painter.drawLine(graph.left(), int(y), graph.right(), int(y))

        if not self.points:
            painter.setPen(QColor("#7f858f"))
            painter.drawText(graph, Qt.AlignCenter, self.empty_message)
            return

        min_time = min(point[0] for point in self.points)
        max_time = max(point[0] for point in self.points)
        max_value = max(max(point[1] for point in self.points), 1.0)
        total_seconds = max((max_time - min_time).total_seconds(), 1.0)

        if max(point[1] for point in self.points) <= 0:
            self._draw_now_marker(painter, graph, min_time, max_time, total_seconds)
            painter.setPen(QColor("#7f858f"))
            painter.drawText(graph, Qt.AlignCenter, self.empty_message)
            return

        mapped = [self._map_point(timestamp, value, min_time, total_seconds, max_value, graph) for timestamp, value in self.points]

        fill_path = QPainterPath(mapped[0])
        for point in mapped[1:]:
            fill_path.lineTo(point)
        fill_path.lineTo(graph.right(), graph.bottom())
        fill_path.lineTo(graph.left(), graph.bottom())
        fill_path.closeSubpath()
        painter.fillPath(fill_path, QColor(201, 151, 0, 58))

        line_path = QPainterPath(mapped[0])
        for point in mapped[1:]:
            line_path.lineTo(point)
        painter.setPen(QPen(QColor("#c99700"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(line_path)

        painter.setPen(QPen(QColor("#d8ae27"), 1, Qt.DashLine))
        painter.setBrush(QBrush(QColor("#d8ae27")))
        for marker in self.markers:
            if marker < min_time or marker > max_time:
                continue
            x_ratio = (marker - min_time).total_seconds() / total_seconds
            x = graph.left() + graph.width() * x_ratio
            painter.drawLine(int(x), graph.top(), int(x), graph.bottom())
            painter.drawEllipse(QPointF(x, graph.bottom()), 4, 4)

        self._draw_now_marker(painter, graph, min_time, max_time, total_seconds)
        
        if self.hover_pos and self.points:
            x = self.hover_pos.x()
            if graph.left() <= x <= graph.right():
                painter.setPen(QPen(QColor("#a0a5af"), 1, Qt.DashLine))
                painter.drawLine(int(x), graph.top(), int(x), graph.bottom())
                
                from datetime import timedelta
                x_ratio = (x - graph.left()) / graph.width()
                hover_time = min_time + timedelta(seconds=total_seconds * x_ratio)
                
                hover_value = 0.0
                for i in range(len(self.points) - 1):
                    if self.points[i][0] <= hover_time <= self.points[i+1][0]:
                        t1, v1 = self.points[i]
                        t2, v2 = self.points[i+1]
                        if (t2 - t1).total_seconds() > 0:
                            ratio = (hover_time - t1).total_seconds() / (t2 - t1).total_seconds()
                            hover_value = v1 + (v2 - v1) * ratio
                        else:
                            hover_value = v1
                        break
                
                label = f"{hover_time.strftime('%I:%M %p').lstrip('0')}  |  {hover_value:.2f} active drinks"
                if self.bac_converter is not None:
                    label += f"  |  {self.bac_converter(hover_value):.3f}% BAC"
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.setPen(QColor("#ececef"))
                
                fm = painter.fontMetrics()
                text_width = fm.horizontalAdvance(label)
                text_x = x - text_width / 2
                if text_x < graph.left():
                    text_x = graph.left()
                elif text_x + text_width > graph.right():
                    text_x = graph.right() - text_width
                    
                painter.drawText(int(text_x), graph.top() - 6, label)

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#7f858f"))
        bottom = graph.adjusted(0, graph.height() + 8, 0, 28)
        painter.drawText(bottom, Qt.AlignLeft, min_time.strftime("%b %d %I:%M %p"))
        painter.drawText(bottom, Qt.AlignRight, max_time.strftime("%b %d %I:%M %p"))
        painter.drawText(graph.adjusted(0, -22, 0, -graph.height()), Qt.AlignRight, f"Peak {max_value:.1f}")

    def _draw_now_marker(self, painter, graph, min_time, max_time, total_seconds) -> None:
        now = datetime.now()
        if now < min_time or now > max_time:
            return
        x_ratio = (now - min_time).total_seconds() / total_seconds
        x = graph.left() + graph.width() * x_ratio
        painter.setPen(QPen(QColor("#66d9ff"), 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(x), graph.top(), int(x), graph.bottom())
        label_rect = graph.adjusted(0, -24, 0, -graph.height() + 2)
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.setPen(QColor("#66d9ff"))
        painter.drawText(label_rect.adjusted(int(x - graph.left()) - 24, 0, 0, 0), Qt.AlignLeft, "Now")

    def _map_point(self, timestamp, value, min_time, total_seconds, max_value, graph) -> QPointF:
        x_ratio = (timestamp - min_time).total_seconds() / total_seconds
        y_ratio = min(value / max_value, 1.0)
        return QPointF(
            graph.left() + graph.width() * x_ratio,
            graph.bottom() - graph.height() * y_ratio,
        )


class StatCard(QFrame):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        self.value = QLabel("--")
        self.value.setObjectName("StatValue")
        self.label = QLabel(label)
        self.label.setObjectName("Muted")
        layout.addWidget(self.value)
        layout.addWidget(self.label)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class MainWindow(QMainWindow):
    def __init__(self, store: IngestionStore | None = None) -> None:
        super().__init__()
        if store is None:
            store = IngestionStore(default_db_path())
        self.store = store
        self.settings = load_estimate_settings()
        self.current_ingestions: list[Ingestion] = []
        self.current_consumer = "All"
        self._auto_follow_night = True
        self.selected_day = self._natural_selected_day()

        self.setWindowTitle("Alcohol Tracker")
        self.resize(1280, 820)
        self.setMinimumSize(1020, 680)
        self.setCentralWidget(self._build_content())
        self.now_timer = QTimer(self)
        self.now_timer.setInterval(60_000)
        self.now_timer.timeout.connect(self.refresh_time_sensitive_views)
        self.now_timer.start()
        self.refresh_all()

    def _build_content(self) -> QWidget:
        root = QWidget()
        layout = QGridLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)

        self.day_title = QLabel("Today")
        self.day_title.setObjectName("Title")
        self.day_summary = QLabel("No ingestions logged yet")
        self.day_summary.setObjectName("Muted")
        self.days_list = QListWidget()
        self.ingestion_list = QListWidget()
        self.effect_graph = TimelineGraph("Effect Timeline", "Estimated active standard drinks stacked over time.")
        self.effect_graph.set_bac_converter(
            lambda value: estimate_bac(
                value,
                self.settings.user_weight_lbs,
                self.settings.user_gender,
                self.settings.standard_drink_pure_alcohol_oz,
            )
        )
        self.tolerance_graph = TimelineGraph("Tolerance Trend", "Recent-use score with configurable decay.")
        self.total_card = StatCard("standard drinks")
        self.active_card = StatCard("active now")
        self.bac_card = StatCard("est. BAC %")
        self.peak_card = StatCard("estimated peak")
        self.clear_card = StatCard("near zero")

        layout.addWidget(self._build_header(), 0, 0, 1, 2)
        layout.addWidget(self._build_sidebar(), 1, 0)
        layout.addWidget(self._build_main_panel(), 1, 1)
        return root

    def _build_header(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Alcohol Tracker")
        title.setObjectName("Title")
        subtitle = QLabel("Local dark-mode journal with editable ingestion history")
        subtitle.setObjectName("Muted")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.open_settings)
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_data)
        import_button = QPushButton("Import")
        import_button.clicked.connect(self.import_data)
        add_button = QPushButton("+ Ingestion")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_ingestion)
        edit_button = QPushButton("Edit Selected")
        edit_button.clicked.connect(self.edit_selected_ingestion)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_selected_ingestion)

        self.quick_add_row = QWidget()
        self.quick_add_layout = QHBoxLayout(self.quick_add_row)
        self.quick_add_layout.setContentsMargins(0, 8, 0, 0)

        top_row = QHBoxLayout()
        top_row.addLayout(text_layout)
        top_row.addStretch(1)
        top_row.addWidget(import_button)
        top_row.addWidget(export_button)
        top_row.addWidget(settings_button)
        top_row.addWidget(delete_button)
        top_row.addWidget(edit_button)
        top_row.addWidget(add_button)

        layout.addLayout(top_row)
        layout.addWidget(self.quick_add_row)
        self.refresh_quick_add_row()
        return frame

    def refresh_quick_add_row(self) -> None:
        while self.quick_add_layout.count():
            item = self.quick_add_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        presets = self.store.list_presets()
        self.quick_add_row.setVisible(True)

        for preset in presets[:6]:
            btn = QPushButton(f"+ {preset.name}")
            btn.clicked.connect(lambda checked, p=preset: self.quick_add(p))
            self.quick_add_layout.addWidget(btn)

        self.quick_add_combo = QComboBox()
        self.quick_add_combo.setMinimumWidth(220)
        for preset in presets:
            unit = "shots" if preset.unit == "shots" else "fl oz"
            self.quick_add_combo.addItem(
                f"{preset.name}  ({preset.amount:g} {unit}, {preset.abv_percent:g}%)",
                preset.id,
            )
        self.quick_add_layout.addWidget(self.quick_add_combo)

        quick_add_custom_button = QPushButton("Quick Add")
        quick_add_custom_button.setEnabled(bool(presets))
        quick_add_custom_button.clicked.connect(self._quick_add_from_dropdown)
        self.quick_add_layout.addWidget(quick_add_custom_button)

        new_custom_drink_button = QPushButton("+ New Custom Drink")
        new_custom_drink_button.clicked.connect(self.new_custom_drink)
        self.quick_add_layout.addWidget(new_custom_drink_button)

        self.quick_add_layout.addStretch(1)

    def _quick_add_from_dropdown(self) -> None:
        preset_id = self.quick_add_combo.currentData()
        preset = next((p for p in self.store.list_presets() if p.id == preset_id), None)
        if preset is not None:
            self.quick_add(preset)

    def new_custom_drink(self) -> None:
        dialog = PresetDialog(self)
        if dialog.exec():
            preset = dialog.preset()
            self.store.save_preset(preset)
            self.refresh_quick_add_row()
            self._select_quick_add_preset_by_name(preset.name)

    def _select_quick_add_preset_by_name(self, name: str) -> None:
        for index in range(self.quick_add_combo.count()):
            preset_id = self.quick_add_combo.itemData(index)
            preset = next((p for p in self.store.list_presets() if p.id == preset_id), None)
            if preset and preset.name == name:
                self.quick_add_combo.setCurrentIndex(index)
                return

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        frame.setFixedWidth(290)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Drinking Days")
        title.setObjectName("SectionTitle")
        hint = QLabel("Select a day to review its chart and edit entries.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.days_list.currentRowChanged.connect(self.select_day_by_row)
        self.days_list.itemClicked.connect(lambda item: self.select_day_by_row(self.days_list.row(item)))

        self.consumer_filter = QComboBox()
        self.consumer_filter.currentTextChanged.connect(self.set_consumer)
        self._refresh_consumer_filter()

        layout.addWidget(title)
        layout.addWidget(self.consumer_filter)
        layout.addWidget(hint)
        layout.addWidget(self.days_list, 1)
        return frame

    def _build_main_panel(self) -> QWidget:
        frame = QWidget()
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(2, 1)

        stats = QWidget()
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(10)
        for card in (self.total_card, self.active_card, self.bac_card, self.peak_card, self.clear_card):
            stats_layout.addWidget(card)

        list_panel = QFrame()
        list_panel.setObjectName("Panel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(14, 14, 14, 14)
        list_layout.setSpacing(10)
        list_layout.addWidget(self.day_title)
        list_layout.addWidget(self.day_summary)
        list_layout.addWidget(stats)
        list_layout.addWidget(self.ingestion_list, 1)
        self.ingestion_list.itemDoubleClicked.connect(lambda _: self.edit_selected_ingestion())

        layout.addWidget(self.effect_graph, 0, 0)
        layout.addWidget(self.tolerance_graph, 0, 1)
        layout.addWidget(list_panel, 1, 0, 2, 2)
        return frame

    def refresh_all(self) -> None:
        self.refresh_days()
        self.refresh_selected_day()
        self.refresh_tolerance_graph()

    def refresh_time_sensitive_views(self) -> None:
        if self._auto_follow_night:
            natural_day = self._natural_selected_day()
            if natural_day.date() != self.selected_day.date():
                self.selected_day = natural_day
                self.refresh_days()
        self.refresh_selected_day()
        self.refresh_tolerance_graph()

    def _natural_selected_day(self) -> datetime:
        """Yesterday, if its effect curve is still active; otherwise today.

        Keeps the previous night's graph on screen past midnight until the
        drinks from that night have fully cleared, instead of jumping to an
        empty "today" the moment the calendar date changes.
        """
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        ingestions = self.store.list_for_day(yesterday)
        if self.current_consumer != "All":
            ingestions = [i for i in ingestions if i.consumer == self.current_consumer]
        if ingestions:
            points = effect_series(ingestions, yesterday, self.settings)
            if points and points[-1][0] > now:
                return yesterday
        return today

    def refresh_days(self) -> None:
        self.days_list.blockSignals(True)
        self.days_list.clear()
        
        # We fetch all days because if current consumer hasn't drank today, we still want today to appear
        days = self.store.list_days()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if today not in days:
            days.insert(0, today)
        daily_totals = self.store.daily_standard_drinks(self.settings, self.current_consumer)
        
        for day in days:
            total = daily_totals.get(day, 0.0)
            if total == 0.0 and day != today and self.current_consumer != "All":
                continue # Skip empty days for specific consumers (except today)
            label = "Today" if day.date() == today.date() else day.strftime("%a %d %b %Y")
            item = QListWidgetItem(f"{label}\n{total:.2f} standard drinks")
            item.setData(Qt.UserRole, day)
            self.days_list.addItem(item)
            
        row_to_select = 0
        for row in range(self.days_list.count()):
            if self.days_list.item(row).data(Qt.UserRole).date() == self.selected_day.date():
                row_to_select = row
                break
        if self.days_list.count() > 0:
            self.days_list.setCurrentRow(row_to_select)
        self.days_list.blockSignals(False)

    def _refresh_consumer_filter(self) -> None:
        self.consumer_filter.blockSignals(True)
        consumers = ["All"] + self.store.list_consumers()
        current = self.current_consumer
        self.consumer_filter.clear()
        self.consumer_filter.addItems(consumers)
        if current in consumers:
            self.consumer_filter.setCurrentText(current)
        self.consumer_filter.blockSignals(False)

    def set_consumer(self, consumer: str) -> None:
        self.current_consumer = consumer
        self.refresh_all()

    def select_day_by_row(self, row: int) -> None:
        if row < 0:
            return
        day = self.days_list.item(row).data(Qt.UserRole)
        if isinstance(day, datetime):
            self.selected_day = day
            self._auto_follow_night = day.date() == self._natural_selected_day().date()
            self.refresh_selected_day()

    def _session_ingestions_for_day(self, day: datetime) -> list[Ingestion]:
        """All ingestions belonging to any drinking session that touches this calendar day.

        A session spanning midnight (still-active curve from the night
        before) is pulled in whole, so the graph doesn't cut off just
        because the calendar date changed.
        """
        ingestions = self.store.list_all()
        if self.current_consumer != "All":
            ingestions = [i for i in ingestions if i.consumer == self.current_consumer]
        sessions = group_into_sessions(ingestions, self.settings)
        target_date = day.date()
        matched: list[Ingestion] = []
        for session in sessions:
            if any(i.occurred_at.date() == target_date for i in session):
                matched.extend(session)
        matched.sort(key=lambda i: i.occurred_at, reverse=True)
        return matched

    def refresh_selected_day(self) -> None:
        self.current_ingestions = self._session_ingestions_for_day(self.selected_day)

        self.ingestion_list.clear()
        for ingestion in self.current_ingestions:
            unit_label = "shots" if ingestion.unit == "shots" else "fl oz"
            duration_text = f" over {int(ingestion.duration_minutes)}m" if ingestion.duration_minutes > 0 else ""
            item = QListWidgetItem(
                f"{ingestion.occurred_at.strftime('%I:%M %p').lstrip('0')}  |  {ingestion.label} ({ingestion.consumer}){duration_text}\n"
                f"{ingestion.amount:g} {unit_label} at {ingestion.abv_percent:g}% ABV  |  "
                f"{ingestion.standard_drinks(self.settings):.2f} standard drinks  |  {ingestion.pure_alcohol_grams(self.settings):.0f}g ethanol"
            )
            item.setData(Qt.UserRole, ingestion.id)
            self.ingestion_list.addItem(item)

        points = effect_series(self.current_ingestions, self.selected_day, self.settings)
        peak_time, peak = peak_value(points)
        clear_time = estimated_clear_time(points)
        total = sum(item.standard_drinks(self.settings) for item in self.current_ingestions)
        active_now = estimate_active_standard_drinks(self.current_ingestions, datetime.now(), self.settings)
        bac_now = estimate_bac(active_now, self.settings.user_weight_lbs, self.settings.user_gender, self.settings.standard_drink_pure_alcohol_oz)

        self.day_title.setText(self.selected_day.strftime("%a %d %b %Y") + (f" ({self.current_consumer})" if self.current_consumer != "All" else ""))
        self.day_summary.setText(
            f"{len(self.current_ingestions)} ingestions. Estimates use {self.settings.absorption_minutes} min absorption and "
            f"{self.settings.elimination_standard_drinks_per_hour:.2f} standard drinks/hr elimination."
        )
        self.total_card.set_value(f"{total:.2f}")
        self.active_card.set_value(f"{active_now:.2f}")
        self.bac_card.set_value(f"{bac_now:.3f}%")
        self.peak_card.set_value(f"{peak:.2f}" if peak_time else "--")
        self.clear_card.set_value(clear_time.strftime("%I:%M %p").lstrip("0") if clear_time else "--")
        self.effect_graph.set_points(points, [item.occurred_at for item in self.current_ingestions])

    def refresh_tolerance_graph(self) -> None:
        totals = self.store.daily_standard_drinks(self.settings, self.current_consumer)
        self.tolerance_graph.set_points(tolerance_series(totals, datetime.now(), self.settings))

    def add_ingestion(self) -> None:
        dialog = IngestionDialog(
            self,
            presets=self.store.list_presets(),
            save_preset=self.store.save_preset,
            delete_preset=self.store.delete_preset,
        )
        if dialog.exec():
            ingestion = dialog.ingestion()
            self.store.add(ingestion)
            self.selected_day = ingestion.occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
            self.refresh_all()
        self.refresh_quick_add_row()

    def edit_selected_ingestion(self) -> None:
        ingestion = self._selected_ingestion()
        if ingestion is None:
            return
        dialog = IngestionDialog(
            self,
            ingestion,
            presets=self.store.list_presets(),
            save_preset=self.store.save_preset,
            delete_preset=self.store.delete_preset,
        )
        if dialog.exec():
            updated = dialog.ingestion()
            self.store.update(updated)
            self.selected_day = updated.occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
            self.refresh_all()
        self.refresh_quick_add_row()

    def delete_selected_ingestion(self) -> None:
        ingestion = self._selected_ingestion()
        if ingestion is None or ingestion.id is None:
            return
        result = QMessageBox.question(
            self,
            "Delete ingestion",
            "Delete the selected ingestion?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            self.store.delete(ingestion.id)
            self.refresh_all()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.estimate_settings()
            save_estimate_settings(self.settings)
            self.refresh_all()

    def _selected_ingestion(self) -> Ingestion | None:
        item = self.ingestion_list.currentItem()
        if item is None:
            QMessageBox.information(self, "No selection", "Select an ingestion first.")
            return None
        ingestion_id = item.data(Qt.UserRole)
        for ingestion in self.current_ingestions:
            if ingestion.id == ingestion_id:
                return ingestion
        return None

    def quick_add(self, preset) -> None:
        ingestion = Ingestion(
            id=None,
            occurred_at=datetime.now(),
            amount=preset.amount,
            unit=preset.unit,
            abv_percent=preset.abv_percent,
            label=preset.name,
            notes="",
            duration_minutes=0.0,
            consumer="Me",
        )
        self.store.add(ingestion)
        self.selected_day = ingestion.occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
        self.current_consumer = "Me"
        self._refresh_consumer_filter()
        self.refresh_all()

    def export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Data", "", "JSON Files (*.json);;CSV Files (*.csv)")
        if not path:
            return
        
        all_days = self.store.list_days()
        all_ingestions = []
        for day in all_days:
            all_ingestions.extend(self.store.list_for_day(day))
            
        if path.endswith(".csv"):
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Occurred At", "Amount", "Unit", "ABV%", "Label", "Notes", "Duration (min)", "Consumer"])
                for ing in all_ingestions:
                    writer.writerow([
                        ing.occurred_at.isoformat(), ing.amount, ing.unit, ing.abv_percent,
                        ing.label, ing.notes, ing.duration_minutes, ing.consumer
                    ])
        else:
            data = [
                {
                    "occurred_at": ing.occurred_at.isoformat(),
                    "amount": ing.amount,
                    "unit": ing.unit,
                    "abv_percent": ing.abv_percent,
                    "label": ing.label,
                    "notes": ing.notes,
                    "duration_minutes": ing.duration_minutes,
                    "consumer": ing.consumer,
                }
                for ing in all_ingestions
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
        QMessageBox.information(self, "Export Successful", f"Exported {len(all_ingestions)} ingestions to {path}")

    def import_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Data", "", "JSON Files (*.json)")
        if not path:
            return
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not read JSON file: {e}")
            return
            
        # Option C: Skip duplicates based on exact timestamp, amount and label.
        existing = {}
        all_days = self.store.list_days()
        for day in all_days:
            for ing in self.store.list_for_day(day):
                key = (ing.occurred_at.isoformat(timespec="seconds"), ing.amount, ing.label)
                existing[key] = True
                
        imported_count = 0
        skipped_count = 0
        
        for item in data:
            try:
                occurred_at = datetime.fromisoformat(item["occurred_at"])
                key = (occurred_at.isoformat(timespec="seconds"), float(item["amount"]), str(item["label"]))
                if key in existing:
                    skipped_count += 1
                    continue
                    
                ingestion = Ingestion(
                    id=None,
                    occurred_at=occurred_at,
                    amount=float(item["amount"]),
                    unit=str(item["unit"]),
                    abv_percent=float(item["abv_percent"]),
                    label=str(item["label"]),
                    notes=str(item.get("notes", "")),
                    duration_minutes=float(item.get("duration_minutes", 0.0)),
                    consumer=str(item.get("consumer", "Me")),
                )
                self.store.add(ingestion)
                imported_count += 1
            except Exception:
                continue
                
        self._refresh_consumer_filter()
        self.refresh_all()
        QMessageBox.information(self, "Import Complete", f"Imported {imported_count} new ingestions.\nSkipped {skipped_count} duplicates.")





