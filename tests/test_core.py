from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from alcohol_tracker.core.calculations import (
    DrinkPreset,
    Ingestion,
    daily_tolerance_load,
    effect_series,
    estimate_active_standard_drinks,
    estimate_bac,
    group_into_sessions,
    peak_value,
    session_exposure,
    simulate_active_drinks,
    tolerance_multiplier,
    tolerance_multiplier_series,
    tolerance_series,
    total_body_water_litres,
)
from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.core.settings import BAC_MODEL_WIDMARK, EstimateSettings


class CoreTests(unittest.TestCase):
    def test_standard_drink_math_for_one_shot(self) -> None:
        ingestion = Ingestion(
            id=None,
            occurred_at=datetime(2026, 7, 12, 20, 0),
            amount=1.0,
            unit="shots",
            abv_percent=40.0,
            label="Whiskey",
        )

        self.assertAlmostEqual(ingestion.fluid_ounces(), 1.5)
        self.assertAlmostEqual(ingestion.pure_alcohol_oz(), 0.6)
        self.assertAlmostEqual(ingestion.pure_alcohol_grams(), 14.016)
        self.assertAlmostEqual(ingestion.standard_drinks(), 1.0)

    def test_shot_volume_uses_configured_standard_drink_size(self) -> None:
        ingestion = Ingestion(
            id=None,
            occurred_at=datetime(2026, 7, 12, 20, 0),
            amount=2.0,
            unit="shots",
            abv_percent=40.0,
            label="Double shot",
        )
        settings = EstimateSettings(standard_drink_volume_oz=1.0, standard_drink_abv_percent=40.0)

        self.assertAlmostEqual(ingestion.fluid_ounces(settings), 2.0)
        self.assertAlmostEqual(ingestion.standard_drinks(settings), 2.0)

    def test_settings_change_active_estimate(self) -> None:
        occurred_at = datetime.now() - timedelta(hours=2)
        rows = [
            Ingestion(
                id=None,
                occurred_at=occurred_at,
                amount=3.0,
                unit="shots",
                abv_percent=40.0,
                label="Shots",
            )
        ]

        slow = EstimateSettings(elimination_standard_drinks_per_hour=0.3)
        fast = EstimateSettings(elimination_standard_drinks_per_hour=1.2)

        self.assertGreater(
            estimate_active_standard_drinks(rows, datetime.now(), slow),
            estimate_active_standard_drinks(rows, datetime.now(), fast),
        )

    def test_store_round_trip_and_effect_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = IngestionStore(Path(temp_dir) / "test.db")
            occurred_at = datetime.now() - timedelta(minutes=30)
            ingestion = Ingestion(
                id=None,
                occurred_at=occurred_at,
                amount=2.0,
                unit="shots",
                abv_percent=40.0,
                label="Shots",
            )

            store.add(ingestion)
            rows = store.list_for_day(occurred_at)

            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0].standard_drinks(), 2.0)
            self.assertGreater(estimate_active_standard_drinks(rows, datetime.now()), 0)
            self.assertGreater(len(effect_series(rows, occurred_at)), 10)

    def test_custom_presets_can_be_saved_updated_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = IngestionStore(Path(temp_dir) / "test.db")
            self.assertGreaterEqual(len(store.list_presets()), 1)

            store.save_preset(DrinkPreset(None, "My Pour", 2.25, "fl_oz", 45.0))
            saved = next(item for item in store.list_presets() if item.name == "My Pour")
            self.assertEqual(saved.unit, "fl_oz")
            self.assertAlmostEqual(saved.amount, 2.25)

            store.save_preset(DrinkPreset(None, "My Pour", 1.5, "shots", 40.0))
            updated = next(item for item in store.list_presets() if item.name == "My Pour")
            self.assertEqual(updated.unit, "shots")
            self.assertAlmostEqual(updated.amount, 1.5)

            self.assertIsNotNone(updated.id)
            store.delete_preset(updated.id or -1)
            self.assertNotIn("My Pour", [item.name for item in store.list_presets()])

    def test_tolerance_series_decays_forward(self) -> None:
        day = datetime(2026, 7, 1)
        points = tolerance_series({day: 4.0}, day + timedelta(days=14), EstimateSettings(tolerance_half_life_days=7))
        values = {point[0].date(): point[1] for point in points}

        self.assertAlmostEqual(values[day.date()], 4.0)
        self.assertLess(values[(day + timedelta(days=14)).date()], 1.1)

    def test_tolerance_multiplier_is_bounded_and_monotonic(self) -> None:
        settings = EstimateSettings(
            tolerance_max_extra_dose=1.0, tolerance_half_saturation_exposure=3.0
        )

        self.assertAlmostEqual(tolerance_multiplier(0.0, settings), 1.0)
        self.assertAlmostEqual(tolerance_multiplier(3.0, settings), 1.5, places=3)
        self.assertLessEqual(tolerance_multiplier(1_000_000.0, settings), 2.0)
        self.assertGreater(tolerance_multiplier(1_000_000.0, settings), 1.999)

        self.assertLess(tolerance_multiplier(0.5, settings), tolerance_multiplier(5.0, settings))

    def test_tolerance_multiplier_series_matches_score_mapping(self) -> None:
        day = datetime(2026, 7, 1)
        settings = EstimateSettings(
            tolerance_half_life_days=7,
            tolerance_max_extra_dose=1.0,
            tolerance_half_saturation_exposure=3.0,
        )
        score_points = tolerance_series({day: 4.0}, day, settings)
        multiplier_points = tolerance_multiplier_series({day: 4.0}, day, settings)

        self.assertEqual(len(score_points), len(multiplier_points))
        for (score_ts, score), (mult_ts, multiplier) in zip(score_points, multiplier_points):
            self.assertEqual(score_ts, mult_ts)
            self.assertAlmostEqual(multiplier, tolerance_multiplier(score, settings))

    # --- pharmacokinetic model ---------------------------------------------

    def _shots(self, count: int, start: datetime, spacing_minutes: int = 45) -> list[Ingestion]:
        return [
            Ingestion(
                id=None,
                occurred_at=start + timedelta(minutes=spacing_minutes * index),
                amount=1.0,
                unit="shots",
                abv_percent=40.0,
                label="Shot",
            )
            for index in range(count)
        ]

    def test_one_drink_peaks_then_clears(self) -> None:
        settings = EstimateSettings()
        start = datetime(2026, 7, 1, 20, 0)
        points = simulate_active_drinks(
            self._shots(1, start), start, start + timedelta(hours=6), settings, step_minutes=5
        )
        peak_at, peak = peak_value(points)

        # Ethanol peaks roughly half an hour to an hour after a single drink...
        self.assertIsNotNone(peak_at)
        minutes_to_peak = (peak_at - start).total_seconds() / 60.0
        self.assertGreater(minutes_to_peak, 20)
        self.assertLess(minutes_to_peak, 90)

        # ...and one standard drink lands near 0.015% BAC.
        self.assertGreater(estimate_bac(peak, settings), 0.010)
        self.assertLess(estimate_bac(peak, settings), 0.025)

        # It should be gone a few hours later, not lingering forever.
        self.assertAlmostEqual(points[-1][1], 0.0, places=6)

    def test_elimination_is_zero_order_on_the_whole_pool(self) -> None:
        """Once absorption is done the curve falls at a constant drinks/hour."""
        settings = EstimateSettings(elimination_standard_drinks_per_hour=0.6)
        start = datetime(2026, 7, 1, 20, 0)
        points = dict(
            simulate_active_drinks(
                self._shots(6, start), start, start + timedelta(hours=20), settings, step_minutes=60
            )
        )

        # Sample two hours well after the last drink finished absorbing.
        first = points[start + timedelta(hours=9)]
        second = points[start + timedelta(hours=10)]
        self.assertGreater(first, 0.6)
        self.assertAlmostEqual(first - second, 0.6, places=2)

    def test_drinking_slowly_lowers_the_peak(self) -> None:
        """The same alcohol spread over a longer session should peak lower."""
        settings = EstimateSettings()
        start = datetime(2026, 7, 1, 20, 0)
        end = start + timedelta(hours=24)

        fast = peak_value(simulate_active_drinks(self._shots(4, start, 20), start, end, settings))[1]
        slow = peak_value(simulate_active_drinks(self._shots(4, start, 120), start, end, settings))[1]
        self.assertGreater(fast, slow)

    def test_watson_model_tracks_body_composition(self) -> None:
        lean = EstimateSettings(user_weight_lbs=150, user_height_cm=190, user_age_years=25)
        stocky = EstimateSettings(user_weight_lbs=150, user_height_cm=160, user_age_years=25)

        # More body water dilutes the same dose, so the taller frame reads lower.
        self.assertGreater(total_body_water_litres(lean), total_body_water_litres(stocky))
        self.assertLess(estimate_bac(3.0, lean), estimate_bac(3.0, stocky))

        # Legacy Widmark ignores height entirely.
        widmark_lean = EstimateSettings(bac_model=BAC_MODEL_WIDMARK, user_height_cm=190)
        widmark_stocky = EstimateSettings(bac_model=BAC_MODEL_WIDMARK, user_height_cm=160)
        self.assertAlmostEqual(estimate_bac(3.0, widmark_lean), estimate_bac(3.0, widmark_stocky))

    # --- tolerance exposure -------------------------------------------------

    def test_exposure_ignores_drinking_below_the_cns_threshold(self) -> None:
        settings = EstimateSettings()
        start = datetime(2026, 7, 1, 20, 0)
        self.assertAlmostEqual(
            session_exposure(self._shots(1, start), settings).exposure_bac_hours, 0.0, places=4
        )

    def test_bingeing_costs_more_tolerance_than_the_same_drinks_spread_out(self) -> None:
        """Eight drinks in one night must outweigh two drinks on four nights."""
        settings = EstimateSettings()
        binge_night = datetime(2026, 7, 1, 20, 0)
        binge = session_exposure(self._shots(8, binge_night), settings).exposure_bac_hours

        spread = sum(
            session_exposure(
                self._shots(2, binge_night + timedelta(days=day)), settings
            ).exposure_bac_hours
            for day in range(4)
        )
        self.assertGreater(binge, spread * 5)

    def test_a_long_absorption_lag_does_not_split_one_night_apart(self) -> None:
        """Drinks still in the stomach must keep the session open.

        With a lag longer than the gap between drinks, nothing has reached the
        bloodstream yet when the next drink is poured. Judging "is the night over"
        on blood alcohol alone therefore split a single night into isolated
        drinks, each too small to register any tolerance exposure at all.
        """
        settings = EstimateSettings(absorption_lag_minutes=45, absorption_minutes=30)
        evening = datetime(2026, 7, 1, 21, 0)
        night = self._shots(5, evening, spacing_minutes=40)

        self.assertEqual(len(group_into_sessions(night, settings)), 1)
        self.assertGreater(session_exposure(night, settings).exposure_bac_hours, 0.0)

    def test_daily_tolerance_load_groups_a_night_that_crosses_midnight(self) -> None:
        settings = EstimateSettings()
        evening = datetime(2026, 7, 1, 22, 0)
        loads = daily_tolerance_load(self._shots(6, evening, 40), settings)

        # One night out is one load entry, filed under the day it started.
        self.assertEqual(list(loads), [datetime(2026, 7, 1)])
        self.assertGreater(loads[datetime(2026, 7, 1)], 0.0)


if __name__ == "__main__":
    unittest.main()
