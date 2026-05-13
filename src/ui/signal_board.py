"""
信号看板 - 展示今日买入/卖出信号
"""
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .styles import (
    COLOR_UP, COLOR_DOWN, COLOR_YELLOW, COLOR_FLAT,
    REC_COLORS, REC_TEXTS, MACD_TEXTS, change_color, score_color, stars,
)

logger = logging.getLogger(__name__)


class SignalBoardTab(QWidget):
    # 触发自动选股的信号（发给主窗口，主窗口转发给 ScannerTab）
    request_auto_screen = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._buy_row_map = {}
        self._sell_row_map = {}
        self._setup_ui()
        self.load_signals()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        lbl = QLabel("今日信号看板")
        lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#f0883e;")
        self.lbl_update = QLabel("最后更新：--")
        self.lbl_update.setStyleSheet("color:#484f58;font-size:12px;")

        btn_screen = QPushButton("🤖  自动选股")
        btn_screen.setObjectName("btnScan")
        btn_screen.setToolTip("立即运行全市场自动选股，筛选出符合策略的股票")
        btn_screen.clicked.connect(self._on_request_screen)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setFixedWidth(70)
        btn_refresh.clicked.connect(self.load_signals)

        toolbar.addWidget(lbl)
        toolbar.addStretch()
        toolbar.addWidget(self.lbl_update)
        toolbar.addWidget(btn_screen)
        toolbar.addWidget(btn_refresh)
        root.addLayout(toolbar)

        # 统计卡片
        root.addWidget(self._build_summary())

        # 空状态引导（没有信号时显示）
        self.empty_hint = self._build_empty_hint()
        root.addWidget(self.empty_hint)

        # 信号表格区（有信号时显示）
        self.tables_frame = QWidget()
        tables_lay = QVBoxLayout(self.tables_frame)
        tables_lay.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        left_frame = QFrame()
        ll = QVBoxLayout(left_frame)
        ll.setContentsMargins(0, 0, 8, 0)
        lbl_buy = QLabel("🔴  买入信号")
        lbl_buy.setStyleSheet(f"font-size:14px;font-weight:bold;color:{COLOR_UP};")
        ll.addWidget(lbl_buy)
        self.tbl_buy = _build_signal_table()
        ll.addWidget(self.tbl_buy)

        right_frame = QFrame()
        rl = QVBoxLayout(right_frame)
        rl.setContentsMargins(8, 0, 0, 0)
        lbl_sell = QLabel("🟢  卖出信号")
        lbl_sell.setStyleSheet(f"font-size:14px;font-weight:bold;color:{COLOR_DOWN};")
        rl.addWidget(lbl_sell)
        self.tbl_sell = _build_signal_table()
        rl.addWidget(self.tbl_sell)

        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([700, 700])
        tables_lay.addWidget(splitter)
        root.addWidget(self.tables_frame)

    def _build_summary(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 10, 20, 10)

        self.card_buy = _Card("今日买入信号", "0", COLOR_UP)
        self.card_sell = _Card("今日卖出信号", "0", COLOR_DOWN)
        self.card_strong = _Card("强烈买入", "0", "#f0883e")
        self.card_7d = _Card("7日累计信号", "0", "#58a6ff")

        cards = [self.card_buy, self.card_sell, self.card_strong, self.card_7d]
        for i, card in enumerate(cards):
            lay.addWidget(card)
            if i < len(cards) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet("color:#21262d;")
                sep.setFixedHeight(28)
                lay.addWidget(sep)
        return frame

    def _build_empty_hint(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border: 1px dashed #30363d;
                border-radius: 10px;
            }
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)

        icon = QLabel("📊")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:48px;background:transparent;")

        lbl1 = QLabel("今日暂无信号")
        lbl1.setAlignment(Qt.AlignCenter)
        lbl1.setStyleSheet("font-size:18px;color:#58a6ff;font-weight:bold;background:transparent;")

        lbl2 = QLabel(
            "系统会自动从全部 A 股中筛选符合买入条件的股票\n"
            "点击下方按钮立即运行选股，或切换到【股票扫描】标签页进行操作"
        )
        lbl2.setAlignment(Qt.AlignCenter)
        lbl2.setStyleSheet("font-size:13px;color:#8b949e;background:transparent;line-height:180%;")
        lbl2.setWordWrap(True)

        btn = QPushButton("🚀  立即运行全市场自动选股")
        btn.setObjectName("btnScan")
        btn.setMinimumWidth(240)
        btn.clicked.connect(self._on_request_screen)

        lay.addWidget(icon)
        lay.addWidget(lbl1)
        lay.addWidget(lbl2)
        lay.addWidget(btn, alignment=Qt.AlignCenter)
        return frame

    # ===== 数据加载 =====

    @pyqtSlot()
    def load_signals(self):
        try:
            signals = self.db.get_today_signals()
            recent = self.db.get_recent_signals(days=7)

            buy_sigs = [s for s in signals if s.get('signal_type') == 'buy']
            sell_sigs = [s for s in signals if s.get('signal_type') == 'sell']
            strong = [s for s in buy_sigs if s.get('recommendation') == 'strong_buy']

            # 统计卡片
            self.card_buy.set_value(str(len(buy_sigs)))
            self.card_sell.set_value(str(len(sell_sigs)))
            self.card_strong.set_value(str(len(strong)))
            self.card_7d.set_value(str(len(recent)))
            self.lbl_update.setText(f"最后更新：{datetime.now().strftime('%H:%M:%S')}")

            has_signal = bool(buy_sigs or sell_sigs)
            self.empty_hint.setVisible(not has_signal)
            self.tables_frame.setVisible(has_signal)

            if has_signal:
                self._buy_row_map = _fill_table(self.tbl_buy, buy_sigs)
                self._sell_row_map = _fill_table(self.tbl_sell, sell_sigs)
        except Exception as e:
            logger.error(f"加载信号失败: {e}")

    @pyqtSlot()
    def refresh_signals(self):
        self.load_signals()

    def _on_request_screen(self):
        """通知主窗口切换到扫描 Tab 并触发自动选股"""
        self.request_auto_screen.emit()


# =====================================================================
# 工具
# =====================================================================

def _build_signal_table() -> QTableWidget:
    headers = ["代码", "名称", "现价", "涨跌%", "目标价", "止损价",
               "综合分", "信号强度", "触发理由", "时间"]
    tbl = QTableWidget()
    tbl.setColumnCount(len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.setAlternatingRowColors(True)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    tbl.horizontalHeader().setStretchLastSection(True)
    tbl.verticalHeader().setVisible(False)
    tbl.setShowGrid(True)
    for i, w in enumerate([65, 90, 68, 62, 68, 68, 52, 76, 240, 80]):
        tbl.setColumnWidth(i, w)
    return tbl


def _fill_table(tbl: QTableWidget, signals: list) -> dict:
    """填充信号表格，strong_buy 优先、按总分倒序排列，返回 {symbol: row_index} 映射"""
    # strong_buy 排最前，其余按 total_score 倒序
    sorted_sigs = sorted(
        signals,
        key=lambda s: (
            1 if s.get('recommendation') == 'strong_buy' else 0,
            s.get('total_score') or 0,
        ),
        reverse=True,
    )

    row_map = {}
    tbl.setRowCount(len(sorted_sigs))
    for row, s in enumerate(sorted_sigs):
        change    = s.get('change_pct') or 0
        score     = s.get('total_score') or 0
        strength  = s.get('signal_strength') or 3
        created   = (s.get('created_at') or '')[-8:] or '--'
        symbol    = s.get('symbol', '')
        is_strong = s.get('recommendation') == 'strong_buy'
        row_map[symbol] = row

        name_text = ('🔥 ' if is_strong else '') + s.get('name', '')
        values = [
            symbol,
            name_text,
            f"{s.get('price', 0):.2f}",
            f"{change:+.2f}%",
            f"{s.get('target_price', 0):.2f}",
            f"{s.get('stop_loss', 0):.2f}",
            f"{score:.1f}",
            stars(strength),
            s.get('reason', ''),
            created,
        ]
        colors = [
            None, None,
            change_color(change), change_color(change),
            COLOR_UP if s.get('signal_type') == 'buy' else COLOR_DOWN,
            COLOR_DOWN,
            score_color(score),
            COLOR_YELLOW,
            None, None,
        ]
        for col, (val, color) in enumerate(zip(values, colors)):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(
                Qt.AlignLeft | Qt.AlignVCenter if col >= 8 else Qt.AlignCenter
            )
            if is_strong:
                item.setBackground(QColor('#1f2d1f'))  # 强烈买入：深绿底
            if color:
                item.setForeground(QColor(color))
            tbl.setItem(row, col, item)
    return row_map


class _Card(QWidget):
    def __init__(self, title: str, value: str, color: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 6, 22, 6)
        lay.setAlignment(Qt.AlignCenter)
        self._lbl = QLabel(value)
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setStyleSheet(
            f"font-size:26px;font-weight:bold;color:{color};background:transparent;")
        lbl_t = QLabel(title)
        lbl_t.setAlignment(Qt.AlignCenter)
        lbl_t.setStyleSheet("font-size:11px;color:#8b949e;background:transparent;")
        lay.addWidget(self._lbl)
        lay.addWidget(lbl_t)

    def set_value(self, v: str):
        self._lbl.setText(v)
