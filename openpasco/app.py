import sys

from PySide6.QtWidgets import QApplication

from openpasco.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("OpenPASCO")
    app.setApplicationName("OpenPASCO")
    app.setDesktopFileName("openpasco")  # lets Wayland/GNOME match the window to the menu entry
    app.setStyle("Fusion")  # same look on every desktop theme
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
