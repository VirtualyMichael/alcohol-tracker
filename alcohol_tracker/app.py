import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.ui.main_window import MainWindow
from alcohol_tracker.ui.theme import apply_dark_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Alcohol Tracker")
    app.setOrganizationName("Local")
    apply_dark_theme(app)

    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    store = IngestionStore(local_app_data / "AlcoholTracker" / "alcohol_tracker.db")
    window = MainWindow(store)
    window.show()
    return app.exec()
