"""Grey 'workbench' chrome around a light page area. Selectors are scoped to the main window's own
widgets so dialogs keep the normal look."""

CHROME_QSS = """
QMainWindow { background: #4a4a4a; }
QMainWindow::separator { background: #2f2f2f; width: 2px; height: 2px; }
QMenuBar { background: #6b6b6b; color: #ffffff; }
QMenuBar::item { padding: 4px 9px; background: transparent; }
QMenuBar::item:selected { background: #8a8a8a; }
QMenu { background: #555555; color: #ffffff; border: 1px solid #2f2f2f; }
QMenu::item { padding: 5px 24px; }
QMenu::item:selected { background: #2a82da; }
QMenu::item:disabled { color: #9a9a9a; }
QMenu::separator { height: 1px; background: #444444; margin: 3px 6px; }
QToolBar#main_toolbar { background: #757575; border: none; spacing: 4px; padding: 2px; }
QToolBar#main_toolbar QToolButton { color: #ffffff; padding: 3px 7px; border-radius: 3px; }
QToolBar#main_toolbar QToolButton:hover { background: #8f8f8f; }
QToolBar#control_bar { background: #4a4a4a; border: none; border-top: 1px solid #2f2f2f; padding: 2px; }
QDockWidget { color: #ffffff; font-weight: bold; }
QDockWidget::title { background: #3b3b3b; padding: 4px 8px; }
QWidget#palette, QWidget#hw_panel { background: #4a4a4a; }
QWidget#hw_panel QLabel, QWidget#control_row QLabel { color: #f0f0f0; }
QToolButton#tool_btn, QToolButton#record_btn, QToolButton#action_btn {
    color: #ffffff; border: none; border-radius: 4px; padding: 4px 2px; font-size: 11px; }
QToolButton#tool_btn:hover, QToolButton#record_btn:hover, QToolButton#action_btn:hover { background: #666666; }
QToolButton#tool_btn:checked { background: #6a6a6a; }
QListWidget#display_list { background: #4a4a4a; color: #ffffff; border: none; font-size: 11px; }
QListWidget#display_list::item { padding: 3px; border-radius: 4px; }
QListWidget#display_list::item:hover { background: #666666; }
QTabBar::tab { background: #7d7d7d; color: #ffffff; padding: 5px 14px; border: 1px solid #555555;
               border-bottom: none; margin-right: 1px; }
QTabBar::tab:selected { background: #ffffff; color: #222222; }
QTabWidget::pane { border: none; background: palette(base); }
QWidget#page { background: palette(base); }
QFrame#display_frame { background: palette(base); border: 1px solid #b5b5b5; }
QLabel#timer { background: #2b2b2b; color: #ffffff; border-radius: 4px; padding: 2px 16px;
               font-family: monospace; font-size: 26px; font-weight: bold; }
QLabel#timer[recording="true"] { color: #ff6b6b; }
QStatusBar { background: #3b3b3b; color: #dddddd; }
"""
