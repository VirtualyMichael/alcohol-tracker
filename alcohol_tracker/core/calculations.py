"""Estimation model for ingested alcohol.

The model is a standard one-compartment pharmacokinetic treatment of ethanol:

* each drink enters the gut, optionally spread over the time spent drinking it,
* it moves gut -> bloodstream by *first-order* absorption (an exponential
  approach to fully absorbed, set by ``absorption_minutes``),
* the bloodstream pool drains by *Michaelis-Menten* elimination, approaching a
  ceiling of ``elimination_standard_drinks_per_hour``.

Elimination looks essentially zero-order for most of a session — alcohol
dehydrogenase is saturated at ordinary drinking concentrations, so the body clears
a roughly fixed amount per hour rather than a fixed fraction, which is why the
curve falls in a straight line. It is only saturable rather than truly zero-order,
though: while blood alcohol is still low, clearance runs measurably slower than the
maximum. That matters at both ends of a session, keeping the liver from
implausibly eating a large fraction of a drink before it has even been absorbed,
and giving the curve its real trailing tail.

Everything downstream (BAC, the effect graph, the tolerance model) reads off the
same simulated pool, so the numbers on screen are always mutually consistent.

None of this is a medical or legal safety measurement. It is a journaling
estimate with user-tunable constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import exp, log

from alcohol_tracker.core.settings import BAC_MODEL_WIDMARK, EstimateSettings

STANDARD_DRINK_PURE_ALCOHOL_OZ = 0.6  # US standard drink; fallback when no settings given
SHOT_VOLUME_OZ = 1.5
ALCOHOL_DENSITY_GRAMS_PER_FL_OZ = 23.36
POUNDS_PER_KILOGRAM = 2.20462

# Ethanol distributes into total body water, so converting a body-water
# concentration into a *blood* concentration scales by the water content of blood.
BLOOD_WATER_FRACTION = 0.806

# `absorption_minutes` is read as "the time by which a single drink is this far
# absorbed", which is what pins down the first-order rate constant.
ABSORPTION_COMPLETION_FRACTION = 0.95

# BAC below which ethanol has essentially no central-nervous-system effect, so it
# drives no tolerance. Used as the floor of the exposure integral.
TOLERANCE_BAC_THRESHOLD = 0.02

# Michaelis constant for alcohol dehydrogenase, as a BAC. Elimination runs at half
# its maximum rate at this concentration, so clearance is markedly slower while
# blood alcohol is still low - both on the way up and in the final tail.
ETHANOL_MICHAELIS_CONSTANT_BAC = 0.0082

# Below this the pool is treated as empty, so the Michaelis-Menten tail (which
# only approaches zero asymptotically) still terminates.
_EMPTY_POOL_STANDARD_DRINKS = 1e-3

# Treat a drink as fully absorbed once this little of it is left in the gut.
_ABSORPTION_SETTLED_FRACTION = 1e-6


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
        return self.pure_alcohol_oz(settings) / max(standard_oz, 1e-9)


# ---------------------------------------------------------------------------
# Body model
# ---------------------------------------------------------------------------


def total_body_water_litres(settings: EstimateSettings | None = None) -> float:
    """Total body water from the Watson (1980) anthropometric regressions.

    Ethanol dissolves in body water, not in fat, so body *composition* — not just
    mass — sets the concentration a given dose produces. Watson's height/age/weight
    regressions are the standard way to estimate that without a body scan, and they
    are what modern forensic BAC work uses in place of Widmark's original fixed
    factors (which came from a small, lean 1930s cohort and overestimate BAC for
    lean or tall people).
    """
    settings = settings or EstimateSettings()
    weight_kg = max(settings.user_weight_lbs, 1.0) / POUNDS_PER_KILOGRAM
    height_cm = max(settings.user_height_cm, 1.0)
    age_years = max(settings.user_age_years, 1.0)

    male_litres = 2.447 - 0.09516 * age_years + 0.1074 * height_cm + 0.3362 * weight_kg
    female_litres = -2.097 + 0.1069 * height_cm + 0.2466 * weight_kg

    gender = settings.user_gender.strip().lower()
    if gender.startswith("m"):
        litres = male_litres
    elif gender.startswith("f"):
        litres = female_litres
    else:
        litres = (male_litres + female_litres) / 2.0
    return max(litres, 1.0)


def body_water_distribution_ratio(settings: EstimateSettings | None = None) -> float:
    """The Widmark distribution ratio *r* implied by the Watson body-water estimate."""
    settings = settings or EstimateSettings()
    weight_kg = max(settings.user_weight_lbs, 1.0) / POUNDS_PER_KILOGRAM
    return total_body_water_litres(settings) / (BLOOD_WATER_FRACTION * weight_kg)


def estimate_bac(active_standard_drinks: float, settings: EstimateSettings | None = None) -> float:
    """Blood alcohol concentration in percent (g ethanol per 100 mL blood)."""
    settings = settings or EstimateSettings()
    if active_standard_drinks <= 0:
        return 0.0

    grams = (
        active_standard_drinks
        * settings.standard_drink_pure_alcohol_oz
        * ALCOHOL_DENSITY_GRAMS_PER_FL_OZ
    )

    if settings.bac_model == BAC_MODEL_WIDMARK:
        # Widmark's original fixed distribution ratios.
        ratio = 0.68 if settings.user_gender.strip().lower().startswith("m") else 0.55
        weight_grams = max(settings.user_weight_lbs, 1.0) * 453.592
        return max(0.0, grams / (weight_grams * ratio) * 100.0)

    # Concentration in body water, scaled to blood, expressed as g/100 mL.
    return max(0.0, BLOOD_WATER_FRACTION * grams / total_body_water_litres(settings) / 10.0)


# ---------------------------------------------------------------------------
# Pharmacokinetic simulation
# ---------------------------------------------------------------------------


def _absorption_rate_constant(settings: EstimateSettings) -> float:
    """First-order gut -> blood rate constant, per minute."""
    minutes = max(float(settings.absorption_minutes), 1.0)
    return -log(1.0 - ABSORPTION_COMPLETION_FRACTION) / minutes


def _cumulative_absorbed(
    ingestion: Ingestion,
    elapsed_minutes: float,
    rate_constant: float,
    lag_minutes: float,
    settings: EstimateSettings,
) -> float:
    """How much of one drink has reached the bloodstream, in standard drinks.

    Closed form rather than numerically integrated. A drink sipped over
    ``duration_minutes`` is a constant-rate input into the gut, and the gut empties
    exponentially, so the amount absorbed is the convolution of the two.
    """
    dose = ingestion.standard_drinks(settings)
    tau = elapsed_minutes - lag_minutes
    if dose <= 0 or tau <= 0:
        return 0.0

    duration = max(ingestion.duration_minutes, 0.0)
    if duration <= 0:
        return dose * (1.0 - exp(-rate_constant * tau))
    if tau <= duration:
        return (dose / duration) * (tau - (1.0 - exp(-rate_constant * tau)) / rate_constant)
    # Written as a difference of decaying terms so the exponent never overflows.
    tail = exp(-rate_constant * (tau - duration)) - exp(-rate_constant * tau)
    return dose - (dose / (rate_constant * duration)) * tail


def _settled_after_minutes(ingestion: Ingestion, settings: EstimateSettings) -> float:
    """Minutes after a drink starts by which it is, for our purposes, fully absorbed."""
    rate_constant = _absorption_rate_constant(settings)
    tail_minutes = -log(_ABSORPTION_SETTLED_FRACTION) / rate_constant
    return (
        max(settings.absorption_lag_minutes, 0.0)
        + max(ingestion.duration_minutes, 0.0)
        + tail_minutes
    )


def _simulate_pool(
    ingestions: list[Ingestion],
    sim_start: datetime,
    sim_end: datetime,
    settings: EstimateSettings,
) -> list[float]:
    """Minute-by-minute standard drinks present in the body, from ``sim_start``.

    Index ``i`` of the result is the pool ``i`` minutes after ``sim_start``.
    Absorption is exact at each step; only the elimination floor at zero is
    integrated numerically, which one-minute steps resolve comfortably.
    """
    sorted_ingestions = sorted(ingestions, key=lambda item: item.occurred_at)
    rate_constant = _absorption_rate_constant(settings)
    lag = max(settings.absorption_lag_minutes, 0.0)
    elimination_per_minute = max(settings.elimination_standard_drinks_per_hour, 0.0) / 60.0

    # The configured elimination rate is the *maximum* rate, reached only once
    # blood alcohol is well above the Michaelis constant. Expressing that constant
    # in pool units lets the whole simulation stay in standard drinks.
    bac_per_drink = estimate_bac(1.0, settings)
    michaelis_pool = (
        ETHANOL_MICHAELIS_CONSTANT_BAC / bac_per_drink if bac_per_drink > 0 else 0.0
    )

    total_minutes = max(int((sim_end - sim_start).total_seconds() // 60), 0)
    settled_at = [
        item.occurred_at + timedelta(minutes=_settled_after_minutes(item, settings))
        for item in sorted_ingestions
    ]

    pool = 0.0
    previous_absorbed = 0.0
    # Drinks before this index are fully absorbed and contribute their whole dose.
    first_unsettled = 0
    settled_total = 0.0

    values = [0.0] * (total_minutes + 1)
    for minute in range(total_minutes + 1):
        current = sim_start + timedelta(minutes=minute)

        while first_unsettled < len(sorted_ingestions) and settled_at[first_unsettled] <= current:
            settled_total += sorted_ingestions[first_unsettled].standard_drinks(settings)
            first_unsettled += 1

        absorbed = settled_total
        for index in range(first_unsettled, len(sorted_ingestions)):
            item = sorted_ingestions[index]
            if item.occurred_at > current:
                break
            absorbed += _cumulative_absorbed(
                item,
                (current - item.occurred_at).total_seconds() / 60.0,
                rate_constant,
                lag,
                settings,
            )

        gained = max(absorbed - previous_absorbed, 0.0)
        previous_absorbed = absorbed
        pool += gained
        pool -= elimination_per_minute * pool / (michaelis_pool + pool) if pool > 0 else 0.0
        if pool < _EMPTY_POOL_STANDARD_DRINKS:
            pool = 0.0
        values[minute] = pool

    return values


def simulate_active_drinks(
    ingestions: list[Ingestion],
    start: datetime,
    end: datetime,
    settings: EstimateSettings | None = None,
    *,
    step_minutes: int = 10,
) -> list[tuple[datetime, float]]:
    """Sample the modelled amount of alcohol in the body between two times."""
    settings = settings or EstimateSettings()
    if end < start:
        end = start

    # Integrate from the first drink so the pool is already correct at `start`.
    sim_start = min([start] + [item.occurred_at for item in ingestions])
    pool = _simulate_pool(ingestions, sim_start, end, settings)

    step = max(int(step_minutes), 1)
    points: list[tuple[datetime, float]] = []
    cursor = start
    while cursor <= end:
        index = int((cursor - sim_start).total_seconds() // 60)
        points.append((cursor, pool[index] if 0 <= index < len(pool) else 0.0))
        cursor += timedelta(minutes=step)
    return points


def estimate_active_standard_drinks(
    ingestions: list[Ingestion],
    when: datetime,
    settings: EstimateSettings | None = None,
) -> float:
    """Standard drinks still in the body at ``when``."""
    settings = settings or EstimateSettings()
    relevant = [item for item in ingestions if item.occurred_at <= when]
    if not relevant:
        return 0.0
    sim_start = min(item.occurred_at for item in relevant)
    return _simulate_pool(relevant, sim_start, when, settings)[-1]


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
        last = max(
            item.occurred_at + timedelta(minutes=max(item.duration_minutes, 0))
            for item in ingestions
        )
        total_drinks = sum(item.standard_drinks(settings) for item in ingestions)
        clearance_hours = total_drinks / max(settings.elimination_standard_drinks_per_hour, 0.1)
        tail_hours = max(8.0, clearance_hours + 2.0 + settings.absorption_lag_minutes / 60.0)
        default_end = last + timedelta(hours=tail_hours)
    else:
        default_start = selected_day.replace(hour=0, minute=0, second=0, microsecond=0)
        default_end = default_start + timedelta(hours=12)

    start = start_override if start_override is not None else default_start
    end = end_override if end_override is not None else default_end
    return simulate_active_drinks(ingestions, start, end, settings, step_minutes=10)


def estimate_unabsorbed_standard_drinks(
    ingestions: list[Ingestion],
    when: datetime,
    settings: EstimateSettings | None = None,
) -> float:
    """Alcohol that has been drunk but has not reached the bloodstream yet.

    A drink still sitting in the stomach is going to have an effect; it just
    hasn't had it yet. Anything deciding whether drinking is "over" has to count
    it, otherwise a long absorption lag makes a round of drinks look like nothing
    happened.
    """
    settings = settings or EstimateSettings()
    rate_constant = _absorption_rate_constant(settings)
    lag = max(settings.absorption_lag_minutes, 0.0)

    total = 0.0
    for item in ingestions:
        if item.occurred_at > when:
            continue
        elapsed = (when - item.occurred_at).total_seconds() / 60.0
        absorbed = _cumulative_absorbed(item, elapsed, rate_constant, lag, settings)
        total += max(item.standard_drinks(settings) - absorbed, 0.0)
    return total


def estimate_alcohol_in_body(
    ingestions: list[Ingestion],
    when: datetime,
    settings: EstimateSettings | None = None,
) -> float:
    """Everything not yet eliminated: in the bloodstream plus still in the stomach.

    Use this, rather than the bloodstream pool alone, to answer "is the drinking
    finished" — otherwise a round poured inside the absorption lag reads as zero.
    """
    settings = settings or EstimateSettings()
    return estimate_active_standard_drinks(
        ingestions, when, settings
    ) + estimate_unabsorbed_standard_drinks(ingestions, when, settings)


def _session_cleared_by(
    session: list[Ingestion],
    when: datetime,
    settings: EstimateSettings,
    threshold: float,
) -> bool:
    last_input = max(
        item.occurred_at + timedelta(minutes=max(item.duration_minutes, 0)) for item in session
    )
    if when <= last_input:
        return False

    # Cheap upper bound first: past this point the session cannot still be active,
    # so long idle gaps cost nothing to classify.
    elimination_per_minute = max(settings.elimination_standard_drinks_per_hour, 0.0) / 60.0
    if elimination_per_minute > 0:
        total_drinks = sum(item.standard_drinks(settings) for item in session)
        tail_minutes = -log(_ABSORPTION_SETTLED_FRACTION) / _absorption_rate_constant(settings)
        latest_possible = last_input + timedelta(
            minutes=max(settings.absorption_lag_minutes, 0.0)
            + tail_minutes
            + total_drinks / elimination_per_minute
        )
        if when >= latest_possible:
            return True

    return estimate_alcohol_in_body(session, when, settings) <= threshold


def group_into_sessions(
    ingestions: list[Ingestion],
    settings: EstimateSettings | None = None,
    threshold: float = 0.05,
) -> list[list[Ingestion]]:
    """Group ingestions into continuous drinking sessions.

    A session keeps accumulating drinks as long as the previous ones haven't
    decayed to (near) zero by the time the next drink happens, so a night that
    runs past midnight stays one session instead of splitting on the calendar.
    """
    settings = settings or EstimateSettings()
    ordered = sorted(ingestions, key=lambda item: item.occurred_at)
    sessions: list[list[Ingestion]] = []
    current: list[Ingestion] = []
    for ingestion in ordered:
        if current and _session_cleared_by(current, ingestion.occurred_at, settings, threshold):
            sessions.append(current)
            current = []
        current.append(ingestion)
    if current:
        sessions.append(current)
    return sessions


# ---------------------------------------------------------------------------
# Tolerance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionExposure:
    """How hard one drinking session pushed on the central nervous system."""

    start: datetime
    peak_bac: float
    peak_at: datetime | None
    exposure_bac_hours: float


def session_exposure(
    session: list[Ingestion],
    settings: EstimateSettings | None = None,
    *,
    step_minutes: int = 5,
) -> SessionExposure:
    """Integrate a session's BAC curve above the CNS threshold.

    Tolerance is neuroadaptation to *exposure*, so what drives it is how high the
    BAC went and for how long — not how many drinks were poured. Integrating
    ``BAC - threshold`` over the session captures both at once, and does so
    superlinearly: doubling the drinks in one night roughly doubles the peak and
    also doubles the time spent above the threshold, so the exposure grows several
    times over. That is what makes one heavy night count for far more than the same
    drinks spread thinly across a week, which matches what is known about binge
    versus spread-out drinking driving neuroadaptation.
    """
    settings = settings or EstimateSettings()
    if not session:
        now = datetime.now()
        return SessionExposure(start=now, peak_bac=0.0, peak_at=None, exposure_bac_hours=0.0)

    start = min(item.occurred_at for item in session)
    last_input = max(
        item.occurred_at + timedelta(minutes=max(item.duration_minutes, 0)) for item in session
    )
    total_drinks = sum(item.standard_drinks(settings) for item in session)
    clearance_hours = total_drinks / max(settings.elimination_standard_drinks_per_hour, 0.1)
    end = last_input + timedelta(hours=clearance_hours + 2.0)

    points = simulate_active_drinks(session, start, end, settings, step_minutes=step_minutes)

    step_hours = max(step_minutes, 1) / 60.0
    peak_bac = 0.0
    peak_at: datetime | None = None
    exposure = 0.0
    for timestamp, active in points:
        bac = estimate_bac(active, settings)
        if bac > peak_bac:
            peak_bac = bac
            peak_at = timestamp
        exposure += max(bac - TOLERANCE_BAC_THRESHOLD, 0.0) * step_hours

    return SessionExposure(
        start=start, peak_bac=peak_bac, peak_at=peak_at, exposure_bac_hours=exposure
    )


def daily_tolerance_load(
    ingestions: list[Ingestion],
    settings: EstimateSettings | None = None,
) -> dict[datetime, float]:
    """CNS exposure per day, in %BAC-hours, keyed by the day each session started."""
    settings = settings or EstimateSettings()
    loads: dict[datetime, float] = {}
    for session in group_into_sessions(ingestions, settings):
        exposure = session_exposure(session, settings)
        day = exposure.start.replace(hour=0, minute=0, second=0, microsecond=0)
        loads[day] = loads.get(day, 0.0) + exposure.exposure_bac_hours
    return loads


def tolerance_series(
    daily_loads: dict[datetime, float],
    end_day: datetime,
    settings: EstimateSettings | None = None,
) -> list[tuple[datetime, float]]:
    """Recency-weighted exposure score per day, decaying with the tolerance half-life."""
    settings = settings or EstimateSettings()
    start_day = end_day - timedelta(days=42)
    points: list[tuple[datetime, float]] = []
    half_life = max(settings.tolerance_half_life_days, 0.25)
    decay_constant = log(2) / half_life

    cursor = start_day.replace(hour=0, minute=0, second=0, microsecond=0)

    # Run forward far enough for the curve to actually reach baseline, so the
    # "back to baseline" marker is always on the chart.
    forward_days = 14.0
    total_recent = sum(daily_loads.values())
    if total_recent > 0:
        epsilon = 0.001
        forward_days = min(
            max(forward_days, half_life * log(max(total_recent, epsilon) / epsilon) / log(2)),
            365.0,
        )
    final_day = (end_day + timedelta(days=forward_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    while cursor <= final_day:
        score = 0.0
        for day, load in daily_loads.items():
            age_days = (cursor.date() - day.date()).days
            if age_days >= 0:
                score += load * exp(-decay_constant * age_days)
        points.append((cursor, score))
        cursor += timedelta(days=1)
    return points


def tolerance_multiplier(score: float, settings: EstimateSettings | None = None) -> float:
    """Dose multiplier needed to match how a drink felt at your tolerance-free baseline.

    Chronic alcohol tolerance comes from CNS neuroadaptation — GABA-A receptor
    downregulation and NMDA receptor upregulation in response to sustained exposure.
    That adaptation is dose- and recency-dependent but it *saturates*: heavy chronic
    drinkers plateau at needing something like 1.5-2.5x the original dose for the
    same effect, rather than needing ever more without limit.

    ``score`` is the recency-weighted CNS exposure from :func:`tolerance_series`, in
    %BAC-hours. It maps onto a bounded multiplier:

        multiplier = 1 + max_extra_dose * (1 - exp(-ln(2) * score / half_saturation))

    ``tolerance_max_extra_dose`` is the ceiling on extra dose the model will ever ask
    for (default 1.0, i.e. at most 2x baseline). ``tolerance_half_saturation_exposure``
    is the score at which half that ceiling is reached; the ln(2) factor makes that
    hold exactly, the way a half-life does. Both are user-tunable, because real
    tolerance varies enormously between people and no formula can measure it directly.
    """
    settings = settings or EstimateSettings()
    half_saturation = max(settings.tolerance_half_saturation_exposure, 1e-3)
    max_extra_dose = max(settings.tolerance_max_extra_dose, 0.0)
    return 1.0 + max_extra_dose * (1.0 - exp(-log(2) * max(score, 0.0) / half_saturation))


def tolerance_multiplier_series(
    daily_loads: dict[datetime, float],
    end_day: datetime,
    settings: EstimateSettings | None = None,
) -> list[tuple[datetime, float]]:
    """Like :func:`tolerance_series`, but expressed as a dose multiplier."""
    settings = settings or EstimateSettings()
    return [
        (timestamp, tolerance_multiplier(score, settings))
        for timestamp, score in tolerance_series(daily_loads, end_day, settings)
    ]


# ---------------------------------------------------------------------------
# Series helpers
# ---------------------------------------------------------------------------


def peak_value(points: list[tuple[datetime, float]]) -> tuple[datetime | None, float]:
    if not points:
        return None, 0.0
    timestamp, value = max(points, key=lambda point: point[1])
    return timestamp, value


def estimated_clear_time(
    points: list[tuple[datetime, float]], threshold: float = 0.05
) -> datetime | None:
    if not points:
        return None
    peak_index = max(range(len(points)), key=lambda index: points[index][1])
    for timestamp, value in points[peak_index:]:
        if value <= threshold:
            return timestamp
    return None
