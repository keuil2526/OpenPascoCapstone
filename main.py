import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("OpenPASCO")
    app.setApplicationName("OpenPASCO")
    app.setStyle("Fusion")  # same look on every desktop theme
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
