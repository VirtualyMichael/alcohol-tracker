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
from alcohol_tracker.core.settings import (
    BAC_MODEL_WATSON,
    BAC_MODEL_WIDMARK,
    EstimateSettings,
)


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


class PresetDialog(QDialog):
    def __init__(self, parent=None, preset: DrinkPreset | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Drink" if preset else "New Custom Drink")
        self.setMinimumWidth(360)
        self.preset_id = preset.id if preset else None

        self.name = QLineEdit(preset.name if preset else "")
        self.name.setPlaceholderText("e.g. My Favorite IPA")

        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.05, 999.0)
        self.amount.setDecimals(2)
        self.amount.setSingleStep(0.5)
        self.amount.setValue(preset.amount if preset else 1.0)

        self.unit = QComboBox()
        self.unit.addItem("Shots (1.5 fl oz each)", "shots")
        self.unit.addItem("Fluid ounces", "fl_oz")
        if preset:
            self.unit.setCurrentIndex(self.unit.findData(preset.unit))

        self.abv = QDoubleSpinBox()
        self.abv.setRange(0.1, 99.9)
        self.abv.setDecimals(1)
        self.abv.setSingleStep(0.5)
        self.abv.setSuffix("%")
        self.abv.setValue(preset.abv_percent if preset else 40.0)

        form = QFormLayout()
        form.addRow("Drink name", self.name)
        form.addRow("Amount", self.amount)
        form.addRow("Unit", self.unit)
        form.addRow("Alcohol by volume", self.abv)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name required", "Enter a name for this drink.")
            return
        self.accept()

    def preset(self) -> DrinkPreset:
        return DrinkPreset(
            id=self.preset_id,
            name=self.name.text().strip(),
            amount=self.amount.value(),
            unit=str(self.unit.currentData()),
            abv_percent=self.abv.value(),
        )


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
        self.absorption.setToolTip(
            "How long a drink takes to be (95%) absorbed into the bloodstream once "
            "absorption starts. Sets the first-order absorption rate."
        )

        self.absorption_lag = QDoubleSpinBox()
        self.absorption_lag.setRange(0.0, 180.0)
        self.absorption_lag.setDecimals(0)
        self.absorption_lag.setSingleStep(5.0)
        self.absorption_lag.setSuffix(" min")
        self.absorption_lag.setValue(settings.absorption_lag_minutes)
        self.absorption_lag.setToolTip(
            "Delay before a drink starts reaching the bloodstream, mostly gastric "
            "emptying. Near 0 on an empty stomach; raise it after a full meal."
        )

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

        self.tolerance_max_extra_dose = QDoubleSpinBox()
        self.tolerance_max_extra_dose.setRange(0.0, 5.0)
        self.tolerance_max_extra_dose.setDecimals(2)
        self.tolerance_max_extra_dose.setSingleStep(0.1)
        self.tolerance_max_extra_dose.setSuffix("x extra")
        self.tolerance_max_extra_dose.setValue(settings.tolerance_max_extra_dose)
        self.tolerance_max_extra_dose.setToolTip(
            "Ceiling on the tolerance curve: max extra dose ever needed to match your baseline, "
            "e.g. 1.0 means at most 2x the dose (1.0 + 1.0x)."
        )

        self.tolerance_half_saturation = QDoubleSpinBox()
        self.tolerance_half_saturation.setRange(0.5, 100.0)
        self.tolerance_half_saturation.setDecimals(1)
        self.tolerance_half_saturation.setDecimals(2)
        self.tolerance_half_saturation.setRange(0.05, 50.0)
        self.tolerance_half_saturation.setSingleStep(0.25)
        self.tolerance_half_saturation.setSuffix(" %BAC-hr")
        self.tolerance_half_saturation.setValue(settings.tolerance_half_saturation_exposure)
        self.tolerance_half_saturation.setToolTip(
            "Recency-weighted CNS exposure (BAC above 0.02% integrated over time) at "
            "which you reach half the tolerance ceiling. Lower = tolerance builds faster.\n"
            "For reference: ~1.0 is drinking 6 units 4 nights a week; ~4.7 is 10 units "
            "5 nights a week."
        )

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

        self.height = QDoubleSpinBox()
        self.height.setRange(100.0, 250.0)
        self.height.setDecimals(0)
        self.height.setSingleStep(1.0)
        self.height.setSuffix(" cm")
        self.height.setValue(settings.user_height_cm)
        self.height_unit = QComboBox()
        self.height_unit.addItems(["cm", "m", "ft/in"])
        self._height_unit = "cm"
        self.height_unit.currentTextChanged.connect(self._height_unit_changed)

        self.age = QDoubleSpinBox()
        self.age.setRange(15.0, 100.0)
        self.age.setDecimals(0)
        self.age.setSingleStep(1.0)
        self.age.setSuffix(" yrs")
        self.age.setValue(settings.user_age_years)

        self.bac_model = QComboBox()
        self.bac_model.addItem("Watson body water (recommended)", BAC_MODEL_WATSON)
        self.bac_model.addItem("Widmark fixed factor (legacy)", BAC_MODEL_WIDMARK)
        self.bac_model.setCurrentIndex(1 if settings.bac_model == BAC_MODEL_WIDMARK else 0)
        self.bac_model.setToolTip(
            "Watson estimates your total body water from height, weight, age and sex, "
            "which is how modern forensic BAC work is done. Widmark uses one fixed "
            "factor per sex and tends to overestimate BAC for lean or tall people.\n"
            "Height and age are only used by the Watson model."
        )

        form = QFormLayout()
        form.addRow("Absorption time", self.absorption)
        form.addRow("Absorption lag (food)", self.absorption_lag)
        form.addRow("Elimination rate", self.elimination)
        form.addRow("Tolerance half-life", self.tolerance_half_life)
        form.addRow("Tolerance ceiling", self.tolerance_max_extra_dose)
        form.addRow("Tolerance half-saturation", self.tolerance_half_saturation)
        form.addRow("Standard drink vol", self.std_volume)
        form.addRow("Standard drink ABV", self.std_abv)
        form.addRow("BAC model", self.bac_model)
        form.addRow("Body weight", self.weight)
        height_row = QHBoxLayout(); height_row.addWidget(self.height); height_row.addWidget(self.height_unit)
        form.addRow("Height", height_row)
        form.addRow("Age", self.age)
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
            absorption_lag_minutes=self.absorption_lag.value(),
            elimination_standard_drinks_per_hour=self.elimination.value(),
            tolerance_half_life_days=self.tolerance_half_life.value(),
            tolerance_max_extra_dose=self.tolerance_max_extra_dose.value(),
            tolerance_half_saturation_exposure=self.tolerance_half_saturation.value(),
            standard_drink_volume_oz=self.std_volume.value(),
            standard_drink_abv_percent=self.std_abv.value(),
            user_weight_lbs=self.weight.value(),
            user_gender=self.gender.currentText(),
            user_height_cm=self._height_cm(),
            user_age_years=self.age.value(),
            bac_model=self.bac_model.currentData(),
        )

    def _height_cm(self) -> float:
        unit = self.height_unit.currentText()
        return self.height.value() * (100 if unit == "m" else 30.48 if unit == "ft/in" else 1)

    def _height_unit_changed(self, unit: str) -> None:
        cm = self.height.value() * (100 if self._height_unit == "m" else 30.48 if self._height_unit == "ft/in" else 1)
        self._height_unit = unit
        if unit == "m": self.height.setRange(1.0, 2.5); self.height.setDecimals(2); self.height.setValue(cm / 100); self.height.setSuffix(" m")
        elif unit == "ft/in": self.height.setRange(3.0, 8.0); self.height.setDecimals(2); self.height.setValue(cm / 30.48); self.height.setSuffix(" ft")
        else: self.height.setRange(100, 250); self.height.setDecimals(0); self.height.setValue(cm); self.height.setSuffix(" cm")
