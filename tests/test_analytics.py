from datetime import date, datetime
import unittest

from alcohol_tracker.core.analytics import (
    average_drinking_days,
    average_standard_drinks_per_day,
    fill_daily_totals,
)


class AnalyticsTests(unittest.TestCase):
    def test_daily_totals_fill_zero_days_and_include_today(self) -> None:
        totals = {
            datetime(2026, 9, 25, 19): 2.5,
            datetime(2026, 9, 27, 20): 1.0,
        }
        self.assertEqual(
            fill_daily_totals(totals, today=date(2026, 9, 28)),
            {
                date(2026, 9, 25): 2.5,
                date(2026, 9, 26): 0.0,
                date(2026, 9, 27): 1.0,
                date(2026, 9, 28): 0.0,
            },
        )

    def test_drinking_day_average_uses_inclusive_calendar_dates(self) -> None:
        totals = {date(2026, 9, 25): 2.0, date(2026, 9, 27): 1.0}
        # Two of four dates drank, normalized to a seven-day week.
        self.assertAlmostEqual(average_drinking_days(totals, date(2026, 9, 25), date(2026, 9, 28)), 3.5)

    def test_drinks_per_day_counts_zero_days_and_range_endpoints(self) -> None:
        totals = {date(2026, 9, 25): 3.0, date(2026, 9, 27): 1.0}
        self.assertAlmostEqual(
            average_standard_drinks_per_day(totals, date(2026, 9, 25), date(2026, 9, 28)),
            1.0,
        )

    def test_empty_history_has_zero_averages(self) -> None:
        self.assertEqual(fill_daily_totals({}, today=date(2026, 9, 28)), {})
        self.assertEqual(
            average_drinking_days({}, date(2026, 9, 25), date(2026, 9, 28)), 0.0
        )
        self.assertEqual(
            average_standard_drinks_per_day({}, date(2026, 9, 25), date(2026, 9, 28)), 0.0
        )


if __name__ == "__main__":
    unittest.main()
