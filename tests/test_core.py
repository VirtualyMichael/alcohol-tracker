from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from alcohol_tracker.core.calculations import (
    DrinkPreset,
    Ingestion,
    effect_series,
    estimate_active_standard_drinks,
    tolerance_series,
)
from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.core.settings import EstimateSettings


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


if __name__ == "__main__":
    unittest.main()
