"""
UI 样式与颜色常量 - 深色专业金融主题
"""

# ===== 主样式表 =====
DARK_STYLE = """
QMainWindow, QDialog {
    background-color: #0d1117;
}
QWidget {
    background-color: #161b22;
    color: #e6edf3;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 13px;
}
/* 标签页 */
QTabWidget::pane {
    border: 1px solid #21262d;
    background-color: #161b22;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #0d1117;
    color: #8b949e;
    padding: 10px 22px;
    border: none;
    font-size: 13px;
    min-width: 110px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #f0883e;
    border-bottom: 2px solid #f0883e;
    background-color: #161b22;
}
QTabBar::tab:hover:!selected {
    color: #c9d1d9;
    background-color: #21262d;
}
/* 表格 */
QTableWidget {
    background-color: #0d1117;
    alternate-background-color: #161b22;
    border: 1px solid #21262d;
    gridline-color: #21262d;
    selection-background-color: #1f6feb33;
    selection-color: #e6edf3;
    border-radius: 4px;
}
QTableWidget::item {
    padding: 6px 8px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #1f6feb44;
    color: #e6edf3;
}
QHeaderView::section {
    background-color: #21262d;
    color: #8b949e;
    padding: 8px 6px;
    border: none;
    border-right: 1px solid #30363d;
    font-weight: bold;
    font-size: 12px;
}
QHeaderView::section:first {
    border-top-left-radius: 4px;
}
/* 按钮 */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 7px 16px;
    border-radius: 6px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
    color: #e6edf3;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton:disabled {
    color: #484f58;
    border-color: #21262d;
}
QPushButton#btnBuy {
    background-color: #da3633;
    border-color: #f85149;
    color: white;
    font-weight: bold;
}
QPushButton#btnBuy:hover { background-color: #f85149; }
QPushButton#btnSell {
    background-color: #1a7f37;
    border-color: #2ea043;
    color: white;
    font-weight: bold;
}
QPushButton#btnSell:hover { background-color: #2ea043; }
QPushButton#btnScan {
    background-color: #1f6feb;
    border-color: #388bfd;
    color: white;
    font-weight: bold;
    font-size: 14px;
    padding: 9px 28px;
}
QPushButton#btnScan:hover { background-color: #388bfd; }
QPushButton#btnRefresh {
    background-color: #21262d;
    border-color: #58a6ff;
    color: #58a6ff;
    font-size: 13px;
    padding: 7px 16px;
}
QPushButton#btnRefresh:hover { background-color: #1f6feb22; border-color: #388bfd; color: #e6edf3; }
QPushButton#btnSettings {
    background-color: transparent;
    border: 1px solid #30363d;
    color: #8b949e;
    padding: 5px 10px;
    font-size: 13px;
}
QPushButton#btnSettings:hover { border-color: #8b949e; color: #e6edf3; }
QPushButton#btnDanger {
    background-color: #6e40c9;
    border-color: #8957e5;
    color: white;
}
QPushButton#btnDanger:hover { background-color: #8957e5; }
/* 输入框 */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #0d1117;
    color: #e6edf3;
    border: 1px solid #30363d;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #1f6feb;
    outline: none;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb44;
    color: #e6edf3;
}
/* 进度条 */
QProgressBar {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
    color: #e6edf3;
    font-size: 12px;
    height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1f6feb, stop:1 #388bfd);
    border-radius: 3px;
}
/* 滚动条 */
QScrollBar:vertical {
    background-color: #0d1117;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #30363d;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background-color: #0d1117;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #30363d;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
/* 分组框 */
QGroupBox {
    background-color: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: #58a6ff;
    font-weight: bold;
    font-size: 13px;
}
/* 标签 */
QLabel { background-color: transparent; }
/* 文本框 */
QTextEdit, QPlainTextEdit {
    background-color: #0d1117;
    color: #e6edf3;
    border: 1px solid #21262d;
    border-radius: 4px;
}
/* 复选框 */
QCheckBox {
    background-color: transparent;
    color: #c9d1d9;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background-color: #0d1117;
}
QCheckBox::indicator:checked {
    background-color: #1f6feb;
    border-color: #388bfd;
    image: none;
}
/* 状态栏 */
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
    font-size: 12px;
    border-top: 1px solid #21262d;
}
/* 菜单 */
QMenuBar {
    background-color: #0d1117;
    color: #c9d1d9;
    border-bottom: 1px solid #21262d;
}
QMenuBar::item:selected { background-color: #21262d; }
QMenu {
    background-color: #161b22;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 4px;
}
QMenu::item:selected { background-color: #21262d; }
QMenu::separator { height: 1px; background-color: #21262d; }
/* 工具提示 */
QToolTip {
    background-color: #161b22;
    color: #e6edf3;
    border: 1px solid #30363d;
    padding: 4px 8px;
    border-radius: 4px;
}
/* 分割线 */
QSplitter::handle { background-color: #21262d; }
/* 框架 */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #21262d;
}
"""

# ===== 颜色常量（A股：红涨绿跌）=====
COLOR_UP = "#f85149"        # 上涨 红色
COLOR_DOWN = "#3fb950"      # 下跌 绿色
COLOR_FLAT = "#8b949e"      # 持平 灰色
COLOR_ACCENT = "#f0883e"    # 主题橙色
COLOR_BLUE = "#58a6ff"      # 蓝色
COLOR_GREEN = "#3fb950"
COLOR_RED = "#f85149"
COLOR_YELLOW = "#e3b341"
COLOR_PURPLE = "#bc8cff"

REC_COLORS = {
    'strong_buy': '#f85149',
    'buy':        '#ff7b72',
    'hold':       '#e3b341',
    'sell':       '#56d364',
    'strong_sell': '#3fb950',
}
REC_TEXTS = {
    'strong_buy': '强烈买入',
    'buy':        '建议买入',
    'hold':       '持有观望',
    'sell':       '建议卖出',
    'strong_sell': '强烈卖出',
}
MACD_TEXTS = {
    'golden_cross': '金叉 ↑',
    'dead_cross':   '死叉 ↓',
    'bullish':      '看多',
    'bearish':      '看空',
    'neutral':      '--',
}


def change_color(pct) -> str:
    try:
        v = float(pct)
        if v > 0:
            return COLOR_UP
        if v < 0:
            return COLOR_DOWN
    except (TypeError, ValueError):
        pass
    return COLOR_FLAT


def score_color(score) -> str:
    """根据综合评分返回颜色"""
    try:
        s = float(score)
        if s >= 75:
            return COLOR_UP
        if s >= 55:
            return COLOR_YELLOW
        return COLOR_DOWN
    except (TypeError, ValueError):
        return COLOR_FLAT


def stars(n: int, total: int = 5) -> str:
    n = max(0, min(n, total))
    return '★' * n + '☆' * (total - n)
