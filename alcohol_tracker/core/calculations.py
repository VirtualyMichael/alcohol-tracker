from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import exp, log

from alcohol_tracker.core.settings import EstimateSettings

STANDARD_DRINK_PURE_ALCOHOL_OZ = 0.6  # Kept as fallback/default if needed
SHOT_VOLUME_OZ = 1.5
ALCOHOL_DENSITY_GRAMS_PER_FL_OZ = 23.36

def estimate_bac(active_standard_drinks: float, weight_lbs: float, gender: str, standard_drink_pure_alcohol_oz: float) -> float:
    if weight_lbs <= 0:
        return 0.0
    r = 0.68 if gender.lower().startswith('m') else 0.55
    weight_grams = weight_lbs * 453.592
    alcohol_grams = active_standard_drinks * standard_drink_pure_alcohol_oz * ALCOHOL_DENSITY_GRAMS_PER_FL_OZ
    bac = (alcohol_grams / (weight_grams * r)) * 100.0
    return max(0.0, bac)



@dataclass(frozen=True)
class DrinkPreset:
    id: int | None
    name: str
    amount: float
    unit: str
    abv_percent: float


@dataclass(frozen=True)
class Ingestion:
    id: int | None
    occurred_at: datetime
    amount: float
    unit: str
    abv_percent: float
    label: str
    notes: str = ""
    duration_minutes: float = 0.0
    consumer: str = "Me"

    def fluid_ounces(self, settings: EstimateSettings | None = None) -> float:
        if self.unit == "shots":
            shot_oz = settings.standard_drink_volume_oz if settings else SHOT_VOLUME_OZ
            return self.amount * shot_oz
        return self.amount

    def pure_alcohol_oz(self, settings: EstimateSettings | None = None) -> float:
        return self.fluid_ounces(settings) * (self.abv_percent / 100.0)

    def pure_alcohol_grams(self, settings: EstimateSettings | None = None) -> float:
        return self.pure_alcohol_oz(settings) * ALCOHOL_DENSITY_GRAMS_PER_FL_OZ

    def standard_drinks(self, settings: EstimateSettings | None = None) -> float:
        standard_oz = settings.standard_drink_pure_alcohol_oz if settings else STANDARD_DRINK_PURE_ALCOHOL_OZ
        return self.pure_alcohol_oz(settings) / standard_oz


def estimate_active_standard_drinks(
    ingestions: list[Ingestion],
    when: datetime,
    settings: EstimateSettings | None = None,
) -> float:
    if not ingestions:
        return 0.0

    settings = settings or EstimateSettings()
    absorption_hours = max(settings.absorption_minutes, 1) / 60.0
    plateau_hours = max(settings.plateau_minutes, 0) / 60.0

    sorted_ingestions = sorted([i for i in ingestions if i.occurred_at <= when], key=lambda x: x.occurred_at)
    if not sorted_ingestions:
        return 0.0

    start_time = sorted_ingestions[0].occurred_at
    total_minutes = int((when - start_time).total_seconds() / 60.0)

    if total_minutes <= 0:
        return 0.0

    elim_per_min = settings.elimination_standard_drinks_per_hour / 60.0
    active_amounts = [0.0] * len(sorted_ingestions)
    prev_absorbed = [0.0] * len(sorted_ingestions)

    current_time = start_time
    for _ in range(total_minutes):
        current_time += timedelta(minutes=1)
        eligible_for_elim = []

        for i, ing in enumerate(sorted_ingestions):
            elapsed_hours = (current_time - ing.occurred_at).total_seconds() / 3600.0
            if elapsed_hours <= 0:
                continue

            duration_hours = max(ing.duration_minutes, 0) / 60.0
            ratio = _smoothstep(min(1.0, elapsed_hours / (absorption_hours + duration_hours)))
            current_absorbed = ing.standard_drinks(settings) * ratio

            delta_absorbed = current_absorbed - prev_absorbed[i]
            if delta_absorbed > 0:
                active_amounts[i] += delta_absorbed
                prev_absorbed[i] = current_absorbed

            delay_hours = absorption_hours + duration_hours + plateau_hours
            if elapsed_hours > delay_hours and active_amounts[i] > 0:
                eligible_for_elim.append(i)

        if eligible_for_elim:
            to_eliminate = elim_per_min
            for i in eligible_for_elim:
                if to_eliminate <= 0:
                    break
                can_eliminate = min(active_amounts[i], to_eliminate)
                active_amounts[i] -= can_eliminate
                to_eliminate -= can_eliminate

    return sum(active_amounts)


def group_into_sessions(
    ingestions: list[Ingestion],
    settings: EstimateSettings | None = None,
    threshold: float = 0.05,
) -> list[list[Ingestion]]:
    """Group ingestions into continuous drinking sessions.

    A session keeps accumulating ingestions as long as the estimated active
    standard drinks from it hasn't decayed to (near) zero by the time the
    next ingestion happens. A new session only starts once the previous
    curve has actually finished, rather than at the midnight calendar
    boundary.
    """
    settings = settings or EstimateSettings()
    ordered = sorted(ingestions, key=lambda item: item.occurred_at)
    sessions: list[list[Ingestion]] = []
    current: list[Ingestion] = []
    for ingestion in ordered:
        if current and estimate_active_standard_drinks(current, ingestion.occurred_at, settings) <= threshold:
            sessions.append(current)
            current = []
        current.append(ingestion)
    if current:
        sessions.append(current)
    return sessions


def effect_series(
    ingestions: list[Ingestion],
    selected_day: datetime,
    settings: EstimateSettings | None = None,
    *,
    start_override: datetime | None = None,
    end_override: datetime | None = None,
) -> list[tuple[datetime, float]]:
    settings = settings or EstimateSettings()
    if ingestions:
        default_start = min(item.occurred_at for item in ingestions) - timedelta(minutes=30)
        last = max(item.occurred_at + timedelta(minutes=item.duration_minutes) for item in ingestions)
        total_drinks = sum(item.standard_drinks(settings) for item in ingestions)
        tail_hours = max(8.0, total_drinks / max(settings.elimination_standard_drinks_per_hour, 0.1) + 2.0 + (settings.plateau_minutes / 60.0))
        default_end = last + timedelta(hours=tail_hours)
    else:
        default_start = selected_day.replace(hour=0, minute=0, second=0, microsecond=0)
        default_end = default_start + timedelta(hours=12)

    start = start_override if start_override is not None else default_start
    end = end_override if end_override is not None else default_end
    if end < start:
        end = start

    sorted_ingestions = sorted(ingestions, key=lambda item: item.occurred_at)
    absorption_hours = max(settings.absorption_minutes, 1) / 60.0
    plateau_hours = max(settings.plateau_minutes, 0) / 60.0
    elim_per_min = settings.elimination_standard_drinks_per_hour / 60.0
    active_amounts = [0.0] * len(sorted_ingestions)
    prev_absorbed = [0.0] * len(sorted_ingestions)

    points: list[tuple[datetime, float]] = []
    cursor = start
    current_time = start
    while cursor <= end:
        while current_time < cursor:
            current_time += timedelta(minutes=1)
            eligible_for_elim = []
            for i, ing in enumerate(sorted_ingestions):
                elapsed_hours = (current_time - ing.occurred_at).total_seconds() / 3600.0
                if elapsed_hours <= 0:
                    continue
                duration_hours = max(ing.duration_minutes, 0) / 60.0
                ratio = _smoothstep(min(1.0, elapsed_hours / (absorption_hours + duration_hours)))
                current_absorbed = ing.standard_drinks(settings) * ratio
                delta_absorbed = current_absorbed - prev_absorbed[i]
                if delta_absorbed > 0:
                    active_amounts[i] += delta_absorbed
                    prev_absorbed[i] = current_absorbed
                delay_hours = absorption_hours + duration_hours + plateau_hours
                if elapsed_hours > delay_hours and active_amounts[i] > 0:
                    eligible_for_elim.append(i)
            if eligible_for_elim:
                to_eliminate = elim_per_min
                for i in eligible_for_elim:
                    if to_eliminate <= 0:
                        break
                    can_eliminate = min(active_amounts[i], to_eliminate)
                    active_amounts[i] -= can_eliminate
                    to_eliminate -= can_eliminate
        points.append((cursor, sum(active_amounts)))
        cursor += timedelta(minutes=10)
    return points


def tolerance_series(
    daily_totals: dict[datetime, float],
    end_day: datetime,
    settings: EstimateSettings | None = None,
) -> list[tuple[datetime, float]]:
    settings = settings or EstimateSettings()
    start_day = end_day - timedelta(days=42)
    points: list[tuple[datetime, float]] = []
    half_life = max(settings.tolerance_half_life_days, 0.25)
    decay_constant = log(2) / half_life

    cursor = start_day.replace(hour=0, minute=0, second=0, microsecond=0)
    final_day = (end_day + timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= final_day:
        score = 0.0
        for day, drinks in daily_totals.items():
            age_days = (cursor.date() - day.date()).days
            if age_days >= 0:
                score += drinks * exp(-decay_constant * age_days)
        points.append((cursor, score))
        cursor += timedelta(days=1)
    return points


def peak_value(points: list[tuple[datetime, float]]) -> tuple[datetime | None, float]:
    if not points:
        return None, 0.0
    timestamp, value = max(points, key=lambda point: point[1])
    return timestamp, value


def estimated_clear_time(points: list[tuple[datetime, float]], threshold: float = 0.05) -> datetime | None:
    if not points:
        return None
    peak_index = max(range(len(points)), key=lambda index: points[index][1])
    for timestamp, value in points[peak_index:]:
        if value <= threshold:
            return timestamp
    return None


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)
