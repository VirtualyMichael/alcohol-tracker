from __future__ import annotations

import json
import csv
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QPointF, QTimer, QDateTime
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from alcohol_tracker.core.calculations import (
    Ingestion,
    daily_tolerance_load,
    effect_series,
    estimated_clear_time,
    estimate_active_standard_drinks,
    estimate_alcohol_in_body,
    estimate_bac,
    group_into_sessions,
    peak_value,
    tolerance_multiplier_series,
)
from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.core.paths import default_db_path
from alcohol_tracker.core.settings import load_estimate_settings, save_estimate_settings
from alcohol_tracker.core.recipes import document as recipe_document, parse as parse_recipes
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
        self.min_value = 0.0
        self.value_formatter = lambda value: f"{value:.1f}"
        self.hover_label_fn = None
        self.reference_marker: tuple[datetime, str] | None = None
        self.axis_date_only = False
        self.setMouseTracking(True)
        self.setMinimumHeight(265)

    def set_bac_converter(self, converter) -> None:
        self.bac_converter = converter

    def set_reference_marker(self, timestamp: datetime | None, text: str) -> None:
        self.reference_marker = (timestamp, text) if timestamp is not None else None
        self.update()

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
        floor = self.min_value
        max_value = max(max(point[1] for point in self.points), floor + 1.0)
        total_seconds = max((max_time - min_time).total_seconds(), 1.0)

        if max(point[1] for point in self.points) <= floor:
            self._draw_now_marker(painter, graph, min_time, max_time, total_seconds)
            self._draw_reference_marker(painter, graph, min_time, max_time, total_seconds)
            painter.setPen(QColor("#7f858f"))
            painter.drawText(graph, Qt.AlignCenter, self.empty_message)
            return

        mapped = [self._map_point(timestamp, value, min_time, total_seconds, max_value, graph, floor) for timestamp, value in self.points]

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
        self._draw_reference_marker(painter, graph, min_time, max_time, total_seconds)

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
                
                if self.hover_label_fn is not None:
                    label = self.hover_label_fn(hover_time, hover_value)
                else:
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
        axis_format = "%b %d" if self.axis_date_only else "%b %d %I:%M %p"
        painter.drawText(bottom, Qt.AlignLeft, min_time.strftime(axis_format))
        painter.drawText(bottom, Qt.AlignRight, max_time.strftime(axis_format))
        painter.drawText(graph.adjusted(0, -22, 0, -graph.height()), Qt.AlignRight, f"Peak {self.value_formatter(max_value)}")

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

    def _draw_reference_marker(self, painter, graph, min_time, max_time, total_seconds) -> None:
        if self.reference_marker is None:
            return
        timestamp, text = self.reference_marker
        if timestamp < min_time or timestamp > max_time:
            return
        x_ratio = (timestamp - min_time).total_seconds() / total_seconds
        x = graph.left() + graph.width() * x_ratio
        painter.setPen(QPen(QColor("#7be08a"), 2, Qt.DashLine, Qt.RoundCap))
        painter.drawLine(int(x), graph.top(), int(x), graph.bottom())

        # Drawn inside the plot so it can never collide with the "Now" label above it.
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.setPen(QColor("#7be08a"))
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        text_x = min(max(x - text_width / 2, graph.left()), graph.right() - text_width)
        painter.drawText(int(text_x), graph.top() + fm.ascent() + 4, text)

    def _map_point(self, timestamp, value, min_time, total_seconds, max_value, graph, floor: float = 0.0) -> QPointF:
        x_ratio = (timestamp - min_time).total_seconds() / total_seconds
        span = max(max_value - floor, 1e-9)
        y_ratio = min(max(value - floor, 0.0) / span, 1.0)
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
        self.effect_graph.set_bac_converter(lambda value: estimate_bac(value, self.settings))
        self.tolerance_graph = TimelineGraph(
            "Tolerance Trend",
            "Dose needed to match your baseline, from recent CNS exposure.",
        )
        self.tolerance_graph.min_value = 1.0
        self.tolerance_graph.value_formatter = lambda value: f"{value:.2f}x"
        self.tolerance_graph.axis_date_only = True
        self.tolerance_graph.empty_message = "No recent drinking — tolerance is at baseline (1.00x)"
        self.tolerance_graph.hover_label_fn = self._tolerance_hover_label

        self._window_is_custom = False
        self._full_window: tuple[datetime, datetime] | None = None
        self.window_from = QDateTimeEdit()
        self.window_from.setCalendarPopup(True)
        self.window_from.setDisplayFormat("MMM d, h:mm AP")
        self.window_to = QDateTimeEdit()
        self.window_to.setCalendarPopup(True)
        self.window_to.setDisplayFormat("MMM d, h:mm AP")
        self.reset_window_btn = QPushButton("Full Session")
        self.reset_window_btn.clicked.connect(self.reset_graph_window)
        self.window_from.dateTimeChanged.connect(self._on_window_edited)
        self.window_to.dateTimeChanged.connect(self._on_window_edited)

        self.total_card = StatCard("standard drinks")
        self.active_card = StatCard("active now")
        self.bac_card = StatCard("est. BAC %")
        self.peak_card = StatCard("estimated peak")
        self.clear_card = StatCard("near zero")
        self.tolerance_card = StatCard("tolerance now")
        self.tolerance_card.setToolTip(
            "Estimated shots of a 40% drink needed today to match how one shot felt "
            "at your tolerance-free baseline."
        )

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
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.days_list)
        recipe_panel = QWidget()
        recipe_layout = QVBoxLayout(recipe_panel)
        recipe_layout.setContentsMargins(0, 0, 0, 0)
        recipe_layout.setSpacing(6)
        recipe_title = QLabel("Recipe Library")
        recipe_title.setObjectName("SectionTitle")
        self.recipe_search = QLineEdit()
        self.recipe_search.setPlaceholderText("Search recipes…")
        self.recipe_search.setClearButtonEnabled(True)
        self.recipe_search.textChanged.connect(self.refresh_recipe_library)
        self.recipe_list = QListWidget()
        self.recipe_list.setToolTip("Built-in and personal recipes. Select one to copy or edit it.")
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        for label, callback in (("Copy", self.copy_recipe), ("Edit", self.edit_recipe), ("Import", self.import_recipes), ("Export", self.export_recipes)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions_layout.addWidget(button)
        recipe_layout.addWidget(recipe_title)
        recipe_layout.addWidget(self.recipe_search)
        recipe_layout.addWidget(self.recipe_list, 1)
        recipe_layout.addWidget(actions)
        splitter.addWidget(recipe_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 260])
        layout.addWidget(splitter, 1)
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
        for card in (
            self.total_card,
            self.active_card,
            self.bac_card,
            self.peak_card,
            self.clear_card,
            self.tolerance_card,
        ):
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

        window_toolbar = QWidget()
        toolbar_layout = QHBoxLayout(window_toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        from_label = QLabel("From")
        from_label.setObjectName("Muted")
        to_label = QLabel("To")
        to_label.setObjectName("Muted")
        toolbar_layout.addWidget(from_label)
        toolbar_layout.addWidget(self.window_from)
        toolbar_layout.addWidget(to_label)
        toolbar_layout.addWidget(self.window_to)
        toolbar_layout.addWidget(self.reset_window_btn)
        toolbar_layout.addStretch(1)

        effect_container = QWidget()
        effect_container_layout = QVBoxLayout(effect_container)
        effect_container_layout.setContentsMargins(0, 0, 0, 0)
        effect_container_layout.setSpacing(6)
        effect_container_layout.addWidget(window_toolbar)
        effect_container_layout.addWidget(self.effect_graph, 1)

        layout.addWidget(effect_container, 0, 0)
        layout.addWidget(self.tolerance_graph, 0, 1)
        layout.addWidget(list_panel, 1, 0, 2, 2)
        return frame

    def refresh_all(self) -> None:
        self.refresh_days()
        self.refresh_recipe_library()
        self.refresh_selected_day()
        self.refresh_tolerance_graph()

    def refresh_time_sensitive_views(self) -> None:
        if self._auto_follow_night:
            natural_day = self._natural_selected_day()
            if natural_day.date() != self.selected_day.date():
                self.selected_day = natural_day
                self._window_is_custom = False
                self.refresh_days()
        self.refresh_selected_day()
        self.refresh_tolerance_graph()

    def refresh_recipe_library(self) -> None:
        current_id = self.recipe_list.currentItem().data(Qt.UserRole) if self.recipe_list.currentItem() else None
        self.recipe_list.clear()
        needle = self.recipe_search.text().casefold().strip()
        for recipe in self.store.list_recipes():
            searchable = " ".join([recipe.name, " ".join(recipe.tags or []), " ".join(str(item.get("name", "")) for item in recipe.ingredients)]).casefold()
            if needle and needle not in searchable:
                continue
            item = QListWidgetItem(recipe.name)
            item.setData(Qt.UserRole, recipe.id)
            self.recipe_list.addItem(item)
            if recipe.id == current_id:
                self.recipe_list.setCurrentItem(item)

    def _selected_recipe(self):
        item = self.recipe_list.currentItem()
        recipe_id = item.data(Qt.UserRole) if item else None
        return next((recipe for recipe in self.store.list_recipes() if recipe.id == recipe_id), None)

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
            self._window_is_custom = False
            self.refresh_selected_day()

    def _ingestions_for_consumer(self) -> list[Ingestion]:
        """Every logged ingestion, narrowed to the consumer currently being viewed."""
        ingestions = self.store.list_all()
        if self.current_consumer == "All":
            return ingestions
        return [item for item in ingestions if item.consumer == self.current_consumer]

    def _session_ingestions_for_day(self, day: datetime) -> list[Ingestion]:
        """All ingestions belonging to any drinking session that touches this calendar day.

        A session spanning midnight (still-active curve from the night
        before) is pulled in whole, so the graph doesn't cut off just
        because the calendar date changed.
        """
        sessions = group_into_sessions(self._ingestions_for_consumer(), self.settings)
        target_date = day.date()
        matched: list[Ingestion] = []
        for session in sessions:
            if any(i.occurred_at.date() == target_date for i in session):
                matched.extend(session)
        matched.sort(key=lambda i: i.occurred_at, reverse=True)
        return matched

    def _empty_day_window(self, day: datetime) -> tuple[datetime | None, datetime | None]:
        """Where a day with no ingestions of its own should start its (empty) graph.

        If the previous calendar day's session already cleared (active
        drinks decayed to ~0) before now, continue the flat line from the
        exact moment it cleared instead of resetting to midnight. If the
        previous day was itself idle, or its session is still active
        (mid-curve past midnight), fall back to the default template.
        """
        previous_day = day - timedelta(days=1)
        previous_ingestions = self._session_ingestions_for_day(previous_day)
        if not previous_ingestions:
            return None, None
        now = datetime.now()
        # Counts drinks still being absorbed too, so a nightcap just before
        # midnight doesn't read as "yesterday already cleared".
        if estimate_alcohol_in_body(previous_ingestions, now, self.settings) > 0.05:
            return None, None
        previous_points = effect_series(previous_ingestions, previous_day, self.settings)
        clear_time = estimated_clear_time(previous_points, threshold=0.05)
        if clear_time is None and previous_points:
            clear_time = previous_points[-1][0]
        if clear_time is None or clear_time >= now:
            return None, None
        return clear_time, now

    @staticmethod
    def _to_qdatetime(value: datetime) -> QDateTime:
        return QDateTime.fromSecsSinceEpoch(int(value.timestamp()))

    @staticmethod
    def _from_qdatetime(value: QDateTime) -> datetime:
        return datetime.fromtimestamp(value.toSecsSinceEpoch())

    def _set_window_fields(self, start: datetime, end: datetime) -> None:
        self.window_from.blockSignals(True)
        self.window_to.blockSignals(True)
        self.window_from.setDateTime(self._to_qdatetime(start))
        self.window_to.setDateTime(self._to_qdatetime(end))
        self.window_from.blockSignals(False)
        self.window_to.blockSignals(False)

    def _on_window_edited(self, _value: QDateTime) -> None:
        self._window_is_custom = True
        self._apply_window()

    def reset_graph_window(self) -> None:
        self._window_is_custom = False
        if self._full_window is not None:
            self._set_window_fields(*self._full_window)
        self._apply_window()

    def refresh_selected_day(self) -> None:
        self.current_ingestions = self._session_ingestions_for_day(self.selected_day)

        if self.current_ingestions:
            full_start_override, full_end_override = None, None
        else:
            full_start_override, full_end_override = self._empty_day_window(self.selected_day)
        full_points = effect_series(
            self.current_ingestions,
            self.selected_day,
            self.settings,
            start_override=full_start_override,
            end_override=full_end_override,
        )
        self._full_window = (full_points[0][0], full_points[-1][0])
        if not self._window_is_custom:
            self._set_window_fields(*self._full_window)

        self._apply_window()

    def _apply_window(self) -> None:
        from_dt = self._from_qdatetime(self.window_from.dateTime())
        to_dt = self._from_qdatetime(self.window_to.dateTime())
        if to_dt < from_dt:
            to_dt = from_dt

        visible_ingestions = [i for i in self.current_ingestions if from_dt <= i.occurred_at <= to_dt]
        points = effect_series(
            visible_ingestions,
            self.selected_day,
            self.settings,
            start_override=from_dt,
            end_override=to_dt,
        )

        self.ingestion_list.clear()
        for ingestion in visible_ingestions:
            unit_label = "shots" if ingestion.unit == "shots" else "fl oz"
            duration_text = f" over {int(ingestion.duration_minutes)}m" if ingestion.duration_minutes > 0 else ""
            item = QListWidgetItem(
                f"{ingestion.occurred_at.strftime('%I:%M %p').lstrip('0')}  |  {ingestion.label} ({ingestion.consumer}){duration_text}\n"
                f"{ingestion.amount:g} {unit_label} at {ingestion.abv_percent:g}% ABV  |  "
                f"{ingestion.standard_drinks(self.settings):.2f} standard drinks  |  {ingestion.pure_alcohol_grams(self.settings):.0f}g ethanol"
            )
            item.setData(Qt.UserRole, ingestion.id)
            self.ingestion_list.addItem(item)

        peak_time, peak = peak_value(points)
        clear_time = estimated_clear_time(points)
        total = sum(item.standard_drinks(self.settings) for item in visible_ingestions)
        active_eval_time = max(from_dt, min(to_dt, datetime.now()))
        active_now = estimate_active_standard_drinks(visible_ingestions, active_eval_time, self.settings)
        bac_now = estimate_bac(active_now, self.settings)

        self.day_title.setText(self.selected_day.strftime("%a %d %b %Y") + (f" ({self.current_consumer})" if self.current_consumer != "All" else ""))
        self.day_summary.setText(
            f"{len(visible_ingestions)} ingestions. Estimates use {self.settings.absorption_minutes} min absorption and "
            f"{self.settings.elimination_standard_drinks_per_hour:.2f} standard drinks/hr elimination."
        )
        self.total_card.set_value(f"{total:.2f}")
        self.active_card.set_value(f"{active_now:.2f}")
        self.bac_card.set_value(f"{bac_now:.3f}%")
        self.peak_card.set_value(f"{peak:.2f}" if peak_time else "--")
        self.clear_card.set_value(clear_time.strftime("%I:%M %p").lstrip("0") if clear_time else "--")
        self.effect_graph.set_points(points, [item.occurred_at for item in visible_ingestions])

    def _tolerance_hover_label(self, hover_time: datetime, hover_value: float) -> str:
        date_text = hover_time.strftime("%a, %b %d %Y")
        return f"{date_text}  |  {hover_value:.2f}x  |  {hover_value:.2f} shots to match 1 baseline 40% shot"

    def refresh_tolerance_graph(self) -> None:
        now = datetime.now()
        loads = daily_tolerance_load(self._ingestions_for_consumer(), self.settings)
        points = tolerance_multiplier_series(loads, now, self.settings)
        self.tolerance_graph.set_points(points)

        baseline_threshold = 1.0 + 0.02 * self.settings.tolerance_max_extra_dose
        clear_time = estimated_clear_time(points, threshold=baseline_threshold)
        label = f"Back to baseline ~{clear_time.strftime('%b %d')}" if clear_time else ""
        self.tolerance_graph.set_reference_marker(clear_time, label)

        today = next((value for stamp, value in points if stamp.date() == now.date()), None)
        self.tolerance_card.set_value(f"{today:.2f}x" if today is not None else "--")

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

    def export_recipes(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Recipes", "recipes.json", "Recipe Files (*.json)")
        if not path: return
        with open(path, "w", encoding="utf-8") as handle: json.dump(recipe_document(self.store.list_recipes()), handle, indent=2)
        QMessageBox.information(self, "Recipes exported", f"Exported {len(self.store.list_recipes())} recipes. Each recipe can also be copied as a readable share card from the recipe library.")

    def copy_recipe(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None: QMessageBox.information(self, "Select a recipe", "Choose a recipe in the library first."); return
        self.clipboard().setText(recipe.share_text())
        QMessageBox.information(self, "Recipe copied", "A readable recipe card and importable share code are on your clipboard.")

    def paste_recipe(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Paste recipe", "Paste a recipe card or Alcohol Tracker share code:")
        if not ok or not text.strip(): return
        try: added, skipped = self.store.import_recipes(parse_recipes(text))
        except Exception as exc: QMessageBox.critical(self, "Recipe import failed", str(exc)); return
        QMessageBox.information(self, "Recipes imported", f"Added {added} recipes; skipped {skipped} exact duplicates.")

    def edit_recipe(self) -> None:
        original = self._selected_recipe()
        if original is None: QMessageBox.information(self, "Select a recipe", "Choose a recipe in the library first."); return
        text, ok = QInputDialog.getMultiLineText(self, "Edit recipe", "Edit the structured recipe data:", json.dumps(recipe_document([original]), indent=2))
        if not ok: return
        try:
            updated = parse_recipes(text)
            if len(updated) != 1: raise ValueError("Edit exactly one recipe at a time.")
            self.store.update_recipe(type(original)(original.id, **updated[0].payload()))
        except Exception as exc: QMessageBox.critical(self, "Recipe update failed", str(exc)); return
        self.refresh_recipe_library()
        QMessageBox.information(self, "Recipe updated", "The recipe was saved locally.")

    def import_recipes(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Recipes", "", "Recipe Files (*.json);;Text Files (*.txt)")
        if not path: return
        try:
            with open(path, encoding="utf-8") as handle: recipes = parse_recipes(handle.read())
            added, skipped = self.store.import_recipes(recipes)
        except Exception as exc:
            QMessageBox.critical(self, "Recipe import failed", str(exc)); return
        self.refresh_recipe_library()
        QMessageBox.information(self, "Recipes imported", f"Added {added} recipes; skipped {skipped} exact duplicates.")

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





