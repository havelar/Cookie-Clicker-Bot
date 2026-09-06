"""Tema visual compartilhado pela interface do Cookie Clicker Bot."""


DARK_STYLESHEET = """
* {
    font-family: "Segoe UI";
    font-size: 12px;
    color: #e7eaf0;
}
QMainWindow, QDialog, QWidget {
    background: #16181d;
}
QGroupBox {
    background: #1e222a;
    border: 1px solid #303744;
    border-radius: 10px;
    margin-top: 13px;
    padding: 14px 10px 10px;
    font-weight: 600;
    color: #cdd7e8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 11px;
    padding: 0 5px;
}
QPushButton {
    background: #2b3442;
    border: 1px solid #3a4658;
    border-radius: 7px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #364257; border-color: #5a6d88; }
QPushButton:pressed { background: #202833; }
QPushButton:disabled { color: #778093; background: #20242b; border-color: #292f38; }
QPushButton#primaryButton { background: #3379dc; border-color: #4b91f2; color: white; }
QPushButton#primaryButton:hover { background: #4589eb; }
QPushButton#dangerButton { background: #c44855; border-color: #e86470; color: white; }
QPushButton#dangerButton:hover { background: #d95764; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #526074; border-radius: 4px; background: #181c23; }
QCheckBox::indicator:checked { background: #3d86e8; border-color: #68a4f4; }
QCheckBox::indicator:disabled { border-color: #303744; background: #232831; }
QDoubleSpinBox, QLineEdit, QTextEdit, QListWidget {
    background: #171b21;
    border: 1px solid #37404e;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #3d86e8;
}
QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QListWidget:focus { border-color: #5799ef; }
QTextEdit { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px; }
QListWidget::item { padding: 7px; border-radius: 4px; }
QListWidget::item:selected { background: #2d5f9f; }
QTabWidget::pane { border: 1px solid #303744; border-radius: 8px; top: -1px; background: #1a1e25; }
QTabBar::tab { background: #20252e; border: 1px solid #303744; border-bottom: none; padding: 9px 16px; margin-right: 3px; border-top-left-radius: 7px; border-top-right-radius: 7px; color: #aeb8c9; }
QTabBar::tab:selected { background: #1a1e25; color: #f0f5ff; border-color: #4c627f; }
QStatusBar { background: #121419; color: #98a4b8; }
QLabel#metricCard {
    background: #202733;
    border: 1px solid #364355;
    border-radius: 8px;
    padding: 8px;
    color: #dce8fa;
    font-weight: 600;
}
QScrollBar:vertical { background: #171b21; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a4453; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
