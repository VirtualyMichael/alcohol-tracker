from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from alcohol_tracker.core.calculations import DrinkPreset, Ingestion
from alcohol_tracker.core.settings import EstimateSettings


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    amount REAL NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('shots', 'fl_oz')),
    abv_percent REAL NOT NULL,
    label TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    duration_minutes REAL NOT NULL DEFAULT 0,
    consumer TEXT NOT NULL DEFAULT 'Me',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingestions_occurred_at
ON ingestions(occurred_at);

CREATE TABLE IF NOT EXISTS drink_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    amount REAL NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('shots', 'fl_oz')),
    abv_percent REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_PRESETS = [
    DrinkPreset(None, "Shot - 40%", 1.0, "shots", 40.0),
    DrinkPreset(None, "Double shot - 40%", 2.0, "shots", 40.0),
    DrinkPreset(None, "Beer - 12 oz 5%", 12.0, "fl_oz", 5.0),
    DrinkPreset(None, "Strong beer - 16 oz 8%", 16.0, "fl_oz", 8.0),
    DrinkPreset(None, "Wine - 5 oz 12%", 5.0, "fl_oz", 12.0),
    DrinkPreset(None, "Hard seltzer - 12 oz 5%", 12.0, "fl_oz", 5.0),
]


class IngestionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            
            # Migrations for existing databases
            try:
                connection.execute("ALTER TABLE ingestions ADD COLUMN duration_minutes REAL NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE ingestions ADD COLUMN consumer TEXT NOT NULL DEFAULT 'Me'")
            except sqlite3.OperationalError:
                pass
                
            connection.commit()
        self._seed_presets()

    def _seed_presets(self) -> None:
        if self.list_presets():
            return
        for preset in DEFAULT_PRESETS:
            self.save_preset(preset)

    def list_days(self) -> list[datetime]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT substr(occurred_at, 1, 10) AS day
                FROM ingestions
                GROUP BY day
                ORDER BY day DESC
                """
            ).fetchall()
        return [datetime.fromisoformat(row["day"]) for row in rows]

    def list_for_day(self, day: datetime) -> list[Ingestion]:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM ingestions
                WHERE occurred_at BETWEEN ? AND ?
                ORDER BY occurred_at DESC
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._row_to_ingestion(row) for row in rows]

    def list_consumers(self) -> list[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT DISTINCT consumer FROM ingestions ORDER BY consumer").fetchall()
        return [str(row["consumer"]) for row in rows] if rows else ["Me"]

    def daily_standard_drinks(self, settings: EstimateSettings | None = None, consumer: str | None = None) -> dict[datetime, float]:
        totals: dict[datetime, float] = {}
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM ingestions").fetchall()
        for row in rows:
            ingestion = self._row_to_ingestion(row)
            if consumer and consumer != "All" and ingestion.consumer != consumer:
                continue
            day = ingestion.occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
            totals[day] = totals.get(day, 0.0) + ingestion.standard_drinks(settings)
        return totals

    def add(self, ingestion: Ingestion) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO ingestions (
                    occurred_at, amount, unit, abv_percent, label, notes, duration_minutes, consumer, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ingestion.occurred_at.isoformat(timespec="seconds"),
                    ingestion.amount,
                    ingestion.unit,
                    ingestion.abv_percent,
                    ingestion.label,
                    ingestion.notes,
                    ingestion.duration_minutes,
                    ingestion.consumer,
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(self, ingestion: Ingestion) -> None:
        if ingestion.id is None:
            raise ValueError("Cannot update ingestion without an id")
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE ingestions
                SET occurred_at = ?, amount = ?, unit = ?, abv_percent = ?,
                    label = ?, notes = ?, duration_minutes = ?, consumer = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    ingestion.occurred_at.isoformat(timespec="seconds"),
                    ingestion.amount,
                    ingestion.unit,
                    ingestion.abv_percent,
                    ingestion.label,
                    ingestion.notes,
                    ingestion.duration_minutes,
                    ingestion.consumer,
                    now,
                    ingestion.id,
                ),
            )
            connection.commit()

    def delete(self, ingestion_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM ingestions WHERE id = ?", (ingestion_id,))
            connection.commit()

    def list_presets(self) -> list[DrinkPreset]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM drink_presets
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_preset(row) for row in rows]

    def save_preset(self, preset: DrinkPreset) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO drink_presets (name, amount, unit, abv_percent, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    amount = excluded.amount,
                    unit = excluded.unit,
                    abv_percent = excluded.abv_percent,
                    updated_at = excluded.updated_at
                """,
                (preset.name, preset.amount, preset.unit, preset.abv_percent, now, now),
            )
            connection.commit()
            return int(cursor.lastrowid or 0)

    def delete_preset(self, preset_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM drink_presets WHERE id = ?", (preset_id,))
            connection.commit()

    def _row_to_ingestion(self, row: sqlite3.Row) -> Ingestion:
        return Ingestion(
            id=int(row["id"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            amount=float(row["amount"]),
            unit=str(row["unit"]),
            abv_percent=float(row["abv_percent"]),
            label=str(row["label"]),
            notes=str(row["notes"]),
            duration_minutes=float(row["duration_minutes"] if "duration_minutes" in row.keys() else 0.0),
            consumer=str(row["consumer"] if "consumer" in row.keys() else "Me"),
        )

    def _row_to_preset(self, row: sqlite3.Row) -> DrinkPreset:
        return DrinkPreset(
            id=int(row["id"]),
            name=str(row["name"]),
            amount=float(row["amount"]),
            unit=str(row["unit"]),
            abv_percent=float(row["abv_percent"]),
        )
