import sys

from PySide6.QtWidgets import QApplication

from alcohol_tracker.core.database import IngestionStore
from alcohol_tracker.core.paths import default_db_path
from alcohol_tracker.core.settings import load_appearance_settings
from alcohol_tracker.ui.main_window import MainWindow
from alcohol_tracker.ui.theme import apply_dark_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Alcohol Tracker")
    app.setOrganizationName("Local")
    appearance = load_appearance_settings()
    apply_dark_theme(app, appearance.colors)

    store = IngestionStore(default_db_path())
    window = MainWindow(store)
    window.show()
    return app.exec()
