from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

from alcohol_tracker.core.settings import DEFAULT_APPEARANCE


def apply_dark_theme(
    app: QApplication,
    colors: dict[str, str] | None = None,
    gradient_colors: list[str] | None = None,
) -> None:
    colors = {**DEFAULT_APPEARANCE, **(colors or {})}
    background, panel = colors["background"], colors["panel"]
    text, muted = colors["text"], colors["muted"]
    accent, graph = colors["accent"], colors["graph"]
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(background))
    palette.setColor(QPalette.WindowText, QColor(text))
    palette.setColor(QPalette.Base, QColor(panel))
    palette.setColor(QPalette.AlternateBase, QColor("#1c1f23"))
    palette.setColor(QPalette.ToolTipBase, QColor("#252930"))
    palette.setColor(QPalette.ToolTipText, QColor("#f4f4f5"))
    palette.setColor(QPalette.Text, QColor(text))
    palette.setColor(QPalette.Button, QColor(panel))
    palette.setColor(QPalette.ButtonText, QColor(text))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor(accent))
    palette.setColor(QPalette.HighlightedText, QColor(background))
    app.setPalette(palette)

    stylesheet = (
        """
        QWidget {
            background: %(background)s;
            color: %(text)s;
            font-family: "Segoe UI";
            font-size: 14px;
        }
        QFrame#Panel {
            background: %(panel)s;
            border: 1px solid %(muted)s;
            border-radius: 8px;
        }
        QFrame#StatCard {
            background: %(panel)s;
            border: 1px solid %(muted)s;
            border-radius: 8px;
        }
        QLabel#Title {
            font-size: 24px;
            font-weight: 700;
        }
        QLabel#SectionTitle {
            font-size: 16px;
            font-weight: 650;
        }
        QLabel#StatValue {
            font-size: 20px;
            font-weight: 700;
            color: %(accent)s;
        }
        QLabel#Muted {
            color: %(muted)s;
        }
        QPushButton {
            background: %(panel)s;
            border: 1px solid %(muted)s;
            border-radius: 6px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #2d323a;
        }
        QPushButton:pressed {
            background: #202329;
        }
        QPushButton#PrimaryButton {
            background: %(accent)s;
            border-color: %(accent)s;
            color: %(background)s;
        }
        QPushButton#PrimaryButton:hover {
            background: %(accent)s;
        }
        QListWidget {
            background: %(panel)s;
            border: none;
            outline: none;
        }
        QListWidget::item {
            border-bottom: 1px solid %(muted)s;
            padding: 10px;
        }
        QListWidget::item:selected {
            background: %(accent)s;
            color: %(background)s;
        }
        QLineEdit, QPlainTextEdit, QComboBox, QDateTimeEdit, QDoubleSpinBox, QSpinBox {
            background: %(panel)s;
            border: 1px solid %(muted)s;
            border-radius: 6px;
            padding: 7px;
            selection-background-color: %(accent)s;
            selection-color: %(background)s;
        }
        QComboBox {
            padding-right: 36px;
        }
        QComboBox::drop-down {
            border-left: 1px solid #3a3f48;
            width: 34px;
        }
        QDoubleSpinBox, QSpinBox {
            padding-right: 34px;
        }
        QDoubleSpinBox::up-button, QSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 32px;
            border-left: 1px solid #3a3f48;
            border-bottom: 1px solid #3a3f48;
            background: #24282e;
        }
        QDoubleSpinBox::down-button, QSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 32px;
            border-left: 1px solid #3a3f48;
            background: #24282e;
        }
        QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background: #303640;
        }
        QDialogButtonBox QPushButton {
            min-width: 88px;
        }
        """ % {"background": background, "panel": panel, "text": text, "muted": muted, "accent": accent, "graph": graph}
    )
    if gradient_colors:
        stops = ",".join(f"stop:{index / (len(gradient_colors) - 1):.2f} {color}" for index, color in enumerate(gradient_colors)) if len(gradient_colors) > 1 else f"stop:0 {gradient_colors[0]},stop:1 {gradient_colors[0]}"
        gradient = f"qlineargradient(x1:0,y1:0,x2:1,y2:0,{stops})"
        stylesheet = stylesheet.replace(
            f"QPushButton#PrimaryButton {{\n            background: {accent};",
            f"QPushButton#PrimaryButton {{\n            background: {gradient};",
        )
    app.setStyleSheet(stylesheet)
