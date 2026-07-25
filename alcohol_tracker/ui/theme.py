from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#101113"))
    palette.setColor(QPalette.WindowText, QColor("#ececef"))
    palette.setColor(QPalette.Base, QColor("#15171a"))
    palette.setColor(QPalette.AlternateBase, QColor("#1c1f23"))
    palette.setColor(QPalette.ToolTipBase, QColor("#252930"))
    palette.setColor(QPalette.ToolTipText, QColor("#f4f4f5"))
    palette.setColor(QPalette.Text, QColor("#ececef"))
    palette.setColor(QPalette.Button, QColor("#23262b"))
    palette.setColor(QPalette.ButtonText, QColor("#f4f4f5"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#c99700"))
    palette.setColor(QPalette.HighlightedText, QColor("#101113"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            background: #101113;
            color: #ececef;
            font-family: "Segoe UI";
            font-size: 14px;
        }
        QFrame#Panel {
            background: #15171a;
            border: 1px solid #343840;
            border-radius: 8px;
        }
        QFrame#StatCard {
            background: #1b1e22;
            border: 1px solid #30343b;
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
            color: #f2c64b;
        }
        QLabel#Muted {
            color: #9da3ad;
        }
        QPushButton {
            background: #24282e;
            border: 1px solid #3a3f48;
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
            background: #d3a000;
            border-color: #d3a000;
            color: #121212;
        }
        QPushButton#PrimaryButton:hover {
            background: #e2b21a;
        }
        QListWidget {
            background: #15171a;
            border: none;
            outline: none;
        }
        QListWidget::item {
            border-bottom: 1px solid #2a2e34;
            padding: 10px;
        }
        QListWidget::item:selected {
            background: #272a2f;
            color: #ffffff;
        }
        QLineEdit, QPlainTextEdit, QComboBox, QDateTimeEdit, QDoubleSpinBox, QSpinBox {
            background: #1b1e22;
            border: 1px solid #3a3f48;
            border-radius: 6px;
            padding: 7px;
            selection-background-color: #c99700;
            selection-color: #101113;
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
        """
    )
