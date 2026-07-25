from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from alcohol_tracker.core.calculations import DrinkPreset, Ingestion
from alcohol_tracker.core.settings import EstimateSettings


class IngestionDialog(QDialog):
    def __init__(
        self,
        parent=None,
        ingestion: Ingestion | None = None,
        presets: list[DrinkPreset] | None = None,
        save_preset: Callable[[DrinkPreset], None] | None = None,
        delete_preset: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Ingestion" if ingestion else "Add Ingestion")
        self.setMinimumWidth(500)
        self.ingestion_id = ingestion.id if ingestion else None
        self.presets = presets or []
        self.save_preset_callback = save_preset
        self.delete_preset_callback = delete_preset

        self.preset_combo = QComboBox()
        self._populate_presets()
        self.preset_combo.currentIndexChanged.connect(self._apply_selected_preset)

        self.label = QLineEdit(ingestion.label if ingestion else "Drink")

        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.05, 999.0)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(0.5)
        self.amount.setValue(ingestion.amount if ingestion else 1.0)

        self.unit = QComboBox()
        self.unit.addItem("Shots (1.5 fl oz each)", "shots")
        self.unit.addItem("Fluid ounces", "fl_oz")
        if ingestion:
            self.unit.setCurrentIndex(self.unit.findData(ingestion.unit))

        self.abv = QDoubleSpinBox()
        self.abv.setRange(0.1, 99.9)
        self.abv.setDecimals(1)
        self.abv.setSingleStep(0.5)
        self.abv.setSuffix("%")
        self.abv.setValue(ingestion.abv_percent if ingestion else 40.0)

        self.occurred_at = QDateTimeEdit()
        self.occurred_at.setCalendarPopup(True)
        self.occurred_at.setDisplayFormat("yyyy-MM-dd h:mm AP")
        timestamp = ingestion.occurred_at if ingestion else datetime.now()
        self.occurred_at.setDateTime(QDateTime(timestamp))

        self.duration = QSpinBox()
        self.duration.setRange(0, 720)
        self.duration.setSingleStep(5)
        self.duration.setSuffix(" min")
        self.duration.setValue(int(ingestion.duration_minutes) if ingestion else 0)
        
        self.consumer = QComboBox()
        self.consumer.setEditable(True)
        self.consumer.addItems(["Me"])
        self.consumer.setCurrentText(ingestion.consumer if ingestion else "Me")

        self.notes = QPlainTextEdit(ingestion.notes if ingestion else "")
        self.notes.setMaximumHeight(110)

        save_preset_button = QPushButton("Save Current as Preset")
        save_preset_button.clicked.connect(self._save_current_as_preset)
        delete_preset_button = QPushButton("Delete Preset")
        delete_preset_button.clicked.connect(self._delete_current_preset)
        preset_actions = QHBoxLayout()
        preset_actions.setContentsMargins(0, 0, 0, 0)
        preset_actions.addWidget(save_preset_button)
        preset_actions.addWidget(delete_preset_button)

        form = QFormLayout()
        form.addRow("Drink preset", self.preset_combo)
        form.addRow("", preset_actions)
        form.addRow("Drink name", self.label)
        form.addRow("Amount", self.amount)
        form.addRow("Unit", self.unit)
        form.addRow("Alcohol by volume", self.abv)
        form.addRow("Ingestion time", self.occurred_at)
        form.addRow("Duration", self.duration)
        form.addRow("Consumer", self.consumer)
        form.addRow("Notes", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def ingestion(self) -> Ingestion:
        return Ingestion(
            id=self.ingestion_id,
            occurred_at=self.occurred_at.dateTime().toPython(),
            amount=self.amount.value(),
            unit=str(self.unit.currentData()),
            abv_percent=self.abv.value(),
            label=self.label.text().strip() or "Drink",
            notes=self.notes.toPlainText().strip(),
            duration_minutes=self.duration.value(),
            consumer=self.consumer.currentText().strip() or "Me",
        )

    def _populate_presets(self) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Custom", None)
        for preset in self.presets:
            unit = "shots" if preset.unit == "shots" else "fl oz"
            self.preset_combo.addItem(
                f"{preset.name}  ({preset.amount:g} {unit}, {preset.abv_percent:g}%)",
                preset.id,
            )
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

    def _apply_selected_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        self.label.setText(preset.name)
        self.amount.setValue(preset.amount)
        self.unit.setCurrentIndex(self.unit.findData(preset.unit))
        self.abv.setValue(preset.abv_percent)

    def _save_current_as_preset(self) -> None:
        if self.save_preset_callback is None:
            return
        default_name = self.label.text().strip() or "New drink preset"
        name, accepted = QInputDialog.getText(self, "Save preset", "Preset name", text=default_name)
        name = name.strip()
        if not accepted or not name:
            return
        preset = DrinkPreset(
            id=None,
            name=name,
            amount=self.amount.value(),
            unit=str(self.unit.currentData()),
            abv_percent=self.abv.value(),
        )
        self.save_preset_callback(preset)
        self.presets = self.parent().store.list_presets() if hasattr(self.parent(), "store") else self.presets
        self._populate_presets()
        self._select_preset_by_name(name)

    def _delete_current_preset(self) -> None:
        if self.delete_preset_callback is None:
            return
        preset = self._selected_preset()
        if preset is None or preset.id is None:
            QMessageBox.information(self, "No preset selected", "Select a saved preset first.")
            return
        result = QMessageBox.question(
            self,
            "Delete preset",
            f"Delete preset '{preset.name}'? Existing ingestions will not be changed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.delete_preset_callback(preset.id)
        self.presets = [item for item in self.presets if item.id != preset.id]
        self._populate_presets()

    def _select_preset_by_name(self, name: str) -> None:
        for index in range(self.preset_combo.count()):
            preset_id = self.preset_combo.itemData(index)
            preset = next((item for item in self.presets if item.id == preset_id), None)
            if preset and preset.name == name:
                self.preset_combo.setCurrentIndex(index)
                return

    def _selected_preset(self) -> DrinkPreset | None:
        preset_id = self.preset_combo.currentData()
        if preset_id is None:
            return None
        return next((preset for preset in self.presets if preset.id == preset_id), None)


class SettingsDialog(QDialog):
    def __init__(self, settings: EstimateSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Estimate Settings")
        self.setMinimumWidth(480)

        help_label = QLabel(
            "These values only change journaling estimates. They are not medical or legal safety measurements."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("Muted")

        self.absorption = QSpinBox()
        self.absorption.setRange(5, 240)
        self.absorption.setSuffix(" min")
        self.absorption.setSingleStep(5)
        self.absorption.setValue(settings.absorption_minutes)

        self.elimination = QDoubleSpinBox()
        self.elimination.setRange(0.1, 2.0)
        self.elimination.setDecimals(2)
        self.elimination.setSingleStep(0.05)
        self.elimination.setSuffix(" drinks/hr")
        self.elimination.setValue(settings.elimination_standard_drinks_per_hour)

        self.tolerance_half_life = QDoubleSpinBox()
        self.tolerance_half_life.setRange(0.5, 60.0)
        self.tolerance_half_life.setDecimals(1)
        self.tolerance_half_life.setSingleStep(0.5)
        self.tolerance_half_life.setSuffix(" days")
        self.tolerance_half_life.setValue(settings.tolerance_half_life_days)
        
        self.plateau = QSpinBox()
        self.plateau.setRange(0, 240)
        self.plateau.setSuffix(" min")
        self.plateau.setSingleStep(5)
        self.plateau.setValue(settings.plateau_minutes)

        self.std_volume = QDoubleSpinBox()
        self.std_volume.setRange(0.1, 100.0)
        self.std_volume.setDecimals(1)
        self.std_volume.setSingleStep(0.5)
        self.std_volume.setSuffix(" fl oz")
        self.std_volume.setValue(settings.standard_drink_volume_oz)

        self.std_abv = QDoubleSpinBox()
        self.std_abv.setRange(0.1, 100.0)
        self.std_abv.setDecimals(1)
        self.std_abv.setSingleStep(1.0)
        self.std_abv.setSuffix("%")
        self.std_abv.setValue(settings.standard_drink_abv_percent)

        self.weight = QDoubleSpinBox()
        self.weight.setRange(50.0, 500.0)
        self.weight.setDecimals(1)
        self.weight.setSingleStep(5.0)
        self.weight.setSuffix(" lbs")
        self.weight.setValue(settings.user_weight_lbs)

        self.gender = QComboBox()
        self.gender.addItems(["M", "F", "Other"])
        self.gender.setCurrentText("M" if settings.user_gender.upper().startswith("M") else "F" if settings.user_gender.upper().startswith("F") else "Other")

        form = QFormLayout()
        form.addRow("Absorption time", self.absorption)
        form.addRow("Peak effect plateau", self.plateau)
        form.addRow("Elimination rate", self.elimination)
        form.addRow("Tolerance half-life", self.tolerance_half_life)
        form.addRow("Standard drink vol", self.std_volume)
        form.addRow("Standard drink ABV", self.std_abv)
        form.addRow("Body weight", self.weight)
        form.addRow("Gender (for BAC calc)", self.gender)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def estimate_settings(self) -> EstimateSettings:
        return EstimateSettings(
            absorption_minutes=self.absorption.value(),
            elimination_standard_drinks_per_hour=self.elimination.value(),
            tolerance_half_life_days=self.tolerance_half_life.value(),
            plateau_minutes=self.plateau.value(),
            standard_drink_volume_oz=self.std_volume.value(),
            standard_drink_abv_percent=self.std_abv.value(),
            user_weight_lbs=self.weight.value(),
            user_gender=self.gender.currentText(),
        )
