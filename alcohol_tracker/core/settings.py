from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings


@dataclass(frozen=True)
class EstimateSettings:
    absorption_minutes: int = 45
    elimination_standard_drinks_per_hour: float = 0.67
    tolerance_half_life_days: float = 7.0
    plateau_minutes: int = 60
    standard_drink_volume_oz: float = 1.5
    standard_drink_abv_percent: float = 40.0
    user_weight_lbs: float = 150.0
    user_gender: str = "M"

    @property
    def standard_drink_pure_alcohol_oz(self) -> float:
        return self.standard_drink_volume_oz * (self.standard_drink_abv_percent / 100.0)


def load_estimate_settings() -> EstimateSettings:
    settings = QSettings()
    return EstimateSettings(
        absorption_minutes=int(settings.value("estimate/absorption_minutes", 45)),
        elimination_standard_drinks_per_hour=float(
            settings.value("estimate/elimination_standard_drinks_per_hour", 0.67)
        ),
        tolerance_half_life_days=float(settings.value("estimate/tolerance_half_life_days", 7.0)),
        plateau_minutes=int(settings.value("estimate/plateau_minutes", 60)),
        standard_drink_volume_oz=float(settings.value("estimate/standard_drink_volume_oz", 1.5)),
        standard_drink_abv_percent=float(settings.value("estimate/standard_drink_abv_percent", 40.0)),
        user_weight_lbs=float(settings.value("estimate/user_weight_lbs", 150.0)),
        user_gender=str(settings.value("estimate/user_gender", "M")),
    )


def save_estimate_settings(values: EstimateSettings) -> None:
    settings = QSettings()
    settings.setValue("estimate/absorption_minutes", values.absorption_minutes)
    settings.setValue(
        "estimate/elimination_standard_drinks_per_hour",
        values.elimination_standard_drinks_per_hour,
    )
    settings.setValue("estimate/tolerance_half_life_days", values.tolerance_half_life_days)
    settings.setValue("estimate/plateau_minutes", values.plateau_minutes)
    settings.setValue("estimate/standard_drink_volume_oz", values.standard_drink_volume_oz)
    settings.setValue("estimate/standard_drink_abv_percent", values.standard_drink_abv_percent)
    settings.setValue("estimate/user_weight_lbs", values.user_weight_lbs)
    settings.setValue("estimate/user_gender", values.user_gender)
