from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

BAC_MODEL_WATSON = "watson"
BAC_MODEL_WIDMARK = "widmark"


@dataclass(frozen=True)
class EstimateSettings:
    # --- Absorption / elimination (one-compartment pharmacokinetics) ---
    absorption_minutes: int = 45
    absorption_lag_minutes: float = 15.0
    elimination_standard_drinks_per_hour: float = 0.67

    # --- Tolerance model ---
    tolerance_half_life_days: float = 7.0
    tolerance_max_extra_dose: float = 1.0
    tolerance_half_saturation_exposure: float = 3.0

    # --- What counts as one "standard drink" for this user ---
    standard_drink_volume_oz: float = 1.5
    standard_drink_abv_percent: float = 40.0

    # --- Body model (drives BAC) ---
    user_weight_lbs: float = 150.0
    user_gender: str = "M"
    user_height_cm: float = 178.0
    user_age_years: float = 30.0
    bac_model: str = BAC_MODEL_WATSON

    @property
    def standard_drink_pure_alcohol_oz(self) -> float:
        return self.standard_drink_volume_oz * (self.standard_drink_abv_percent / 100.0)


def load_estimate_settings() -> EstimateSettings:
    settings = QSettings()
    return EstimateSettings(
        absorption_minutes=int(settings.value("estimate/absorption_minutes", 45)),
        absorption_lag_minutes=float(settings.value("estimate/absorption_lag_minutes", 15.0)),
        elimination_standard_drinks_per_hour=float(
            settings.value("estimate/elimination_standard_drinks_per_hour", 0.67)
        ),
        tolerance_half_life_days=float(settings.value("estimate/tolerance_half_life_days", 7.0)),
        tolerance_max_extra_dose=float(settings.value("estimate/tolerance_max_extra_dose", 1.0)),
        tolerance_half_saturation_exposure=float(
            settings.value("estimate/tolerance_half_saturation_exposure", 3.0)
        ),
        standard_drink_volume_oz=float(settings.value("estimate/standard_drink_volume_oz", 1.5)),
        standard_drink_abv_percent=float(settings.value("estimate/standard_drink_abv_percent", 40.0)),
        user_weight_lbs=float(settings.value("estimate/user_weight_lbs", 150.0)),
        user_gender=str(settings.value("estimate/user_gender", "M")),
        user_height_cm=float(settings.value("estimate/user_height_cm", 178.0)),
        user_age_years=float(settings.value("estimate/user_age_years", 30.0)),
        bac_model=str(settings.value("estimate/bac_model", BAC_MODEL_WATSON)),
    )


def save_estimate_settings(values: EstimateSettings) -> None:
    settings = QSettings()
    settings.setValue("estimate/absorption_minutes", values.absorption_minutes)
    settings.setValue("estimate/absorption_lag_minutes", values.absorption_lag_minutes)
    settings.setValue(
        "estimate/elimination_standard_drinks_per_hour",
        values.elimination_standard_drinks_per_hour,
    )
    settings.setValue("estimate/tolerance_half_life_days", values.tolerance_half_life_days)
    settings.setValue("estimate/tolerance_max_extra_dose", values.tolerance_max_extra_dose)
    settings.setValue(
        "estimate/tolerance_half_saturation_exposure", values.tolerance_half_saturation_exposure
    )
    settings.setValue("estimate/standard_drink_volume_oz", values.standard_drink_volume_oz)
    settings.setValue("estimate/standard_drink_abv_percent", values.standard_drink_abv_percent)
    settings.setValue("estimate/user_weight_lbs", values.user_weight_lbs)
    settings.setValue("estimate/user_gender", values.user_gender)
    settings.setValue("estimate/user_height_cm", values.user_height_cm)
    settings.setValue("estimate/user_age_years", values.user_age_years)
    settings.setValue("estimate/bac_model", values.bac_model)
