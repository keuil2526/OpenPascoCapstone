"""Grey 'workbench' chrome around a light page area. Selectors are scoped to the main window's own
widgets so dialogs keep the normal look."""

CHROME_QSS = """
QMainWindow { background: #666666; }
QMainWindow::separator { background: #3a3a3a; width: 2px; height: 2px; }
QMenuBar { background: #6d6d6d; color: #ffffff; }
QMenuBar::item { padding: 4px 9px; background: transparent; }
QMenuBar::item:selected { background: #8a8a8a; }
QMenu { background: #555555; color: #ffffff; border: 1px solid #2f2f2f; }
QMenu::item { padding: 5px 24px; }
QMenu::item:selected { background: #2a82da; }
QMenu::item:disabled { color: #9a9a9a; }
QMenu::separator { height: 1px; background: #444444; margin: 3px 6px; }
QToolBar#main_toolbar { background: #676767; border: none; border-top: 1px solid #555555; spacing: 6px; padding: 2px 4px; }
QToolBar#main_toolbar QToolButton { color: #ffffff; padding: 3px 7px; border-radius: 3px; }
QToolBar#main_toolbar QToolButton:hover { background: #8f8f8f; }
QToolBar#control_bar { background: #666666; border: none; border-top: 1px solid #3a3a3a; padding: 3px; }
QFrame#ctl_group { background: #5b5b5b; border: 1px solid #525252; border-radius: 8px; }
QFrame#ctl_group QLabel, QFrame#ctl_group QToolButton { background: transparent; }
QDockWidget { color: #ffffff; font-weight: bold; font-size: 11px; }
QDockWidget::title { background: #666666; padding: 4px 6px; }
QWidget#palette, QWidget#hw_panel { background: #666666; }
QWidget#hw_panel QLabel#panel_title { background: #5a5a5a; color: #ffffff; font-size: 15px; padding: 7px 10px; }
QWidget#hw_status_row { background: #666666; }
QWidget#hw_panel QLabel#hw_status { color: #ffffff; font-size: 14px; }
QWidget#hw_panel QLabel#hw_hint { background: #ffffff; color: #333333; padding: 3px 8px; }
QListWidget#device_list { background: #707070; color: #ffffff; border: none; }
QWidget#hw_panel QLabel, QWidget#control_row QLabel { color: #f0f0f0; }
QToolButton#tool_btn, QToolButton#record_btn, QToolButton#action_btn {
    color: #ffffff; border: none; border-radius: 4px; padding: 4px 2px; font-size: 10px; }
QToolButton#tool_btn:hover, QToolButton#record_btn:hover, QToolButton#action_btn:hover { background: #7a7a7a; }
QToolButton#tool_btn:checked { background: #808080; }
QListWidget#display_list { background: #666666; color: #ffffff; border: none; font-size: 11px; }
QListWidget#display_list::item { padding: 3px; border-radius: 4px; }
QListWidget#display_list::item:hover { background: #7a7a7a; }
QToolBar#page_row { background: #b2b2b2; border: none; padding: 0 4px; }
QToolButton#tab_plus { color: #333333; font-size: 16px; padding: 0 8px; }
QTabBar#tab_row { background: #b2b2b2; }
QTabBar { background: #b2b2b2; }
QTabBar::tab { background: #c8c8c8; color: #222222; padding: 5px 14px; border: 1px solid #9a9a9a;
               border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 1px; }
QTabBar::tab:selected { background: #ffffff; color: #222222; }
QTabWidget::pane { border: 10px solid #666666; background: palette(base); }
QWidget#page { background: palette(base); }
QFrame#display_frame { background: palette(base); border: none; }
QWidget#display_bar { background: #e9e9e9; }
QToolButton#graph_tool:checked { background: #c9d9ee; border: 1px solid #8fb0dd; border-radius: 3px; }
QWidget#display_bar QLabel, QWidget#display_bar QCheckBox { color: #333333; }
QToolButton#start_card { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0f0f0, stop:1 #cfcfcf);
    color: #444444; border: 1px solid #bdbdbd; border-radius: 3px; padding: 14px 22px 8px 22px; font-size: 15px; }
QToolButton#start_card:hover { background: #e6edf7; border-color: #7aa7e0; }
QLineEdit#graph_title { background: transparent; border: none; color: #333333; padding: 2px 6px; }
QLabel#timer { background: #2e2e2e; color: #ffffff; border: 1px solid #8b8b8b; border-radius: 6px; padding: 2px 16px;
               font-family: monospace; font-size: 26px; font-weight: bold; }
QLabel#timer[recording="true"] { color: #ff6b6b; }
QStatusBar { background: #5a5a5a; color: #eeeeee; }
"""
