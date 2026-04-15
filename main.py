import os
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CSV Generator 2.0")

    # Apply our stylesheet if it's present
    stylesheet_path = os.path.join(os.path.dirname(__file__), "ui", "app_style.qss")
    if os.path.isfile(stylesheet_path):
        with open(stylesheet_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
