"""
历史记录标签页
展示已平仓的交易记录、统计胜率/收益率、权益曲线
"""
import logging

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.font_manager as fm

import numpy as np
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .styles import COLOR_UP, COLOR_DOWN, COLOR_YELLOW, COLOR_FLAT

logger = logging.getLogger(__name__)

# 尝试设置中文字体
try:
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass


class HistoryTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._setup_ui()
        self.load_data()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        lbl = QLabel("历史交易记录")
        lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#f0883e;")
        btn_refresh = QPushButton("刷新")
        btn_refresh.setFixedWidth(80)
        btn_refresh.clicked.connect(self.load_data)
        toolbar.addWidget(lbl)
        toolbar.addStretch()
        toolbar.addWidget(btn_refresh)
        root.addLayout(toolbar)

        # 统计卡片
        root.addWidget(self._build_stats())

        # 分割：表格 + 图表
        splitter = QSplitter(Qt.Vertical)

        # 交易记录表格
        tbl_frame = QGroupBox("交易明细")
        tbl_lay = QVBoxLayout(tbl_frame)
        self.tbl = self._build_table()
        tbl_lay.addWidget(self.tbl)

        # 权益曲线
        chart_frame = QGroupBox("累计盈亏曲线")
        chart_lay = QVBoxLayout(chart_frame)
        self.canvas = _EquityCanvas()
        chart_lay.addWidget(self.canvas)

        splitter.addWidget(tbl_frame)
        splitter.addWidget(chart_frame)
        splitter.setSizes([400, 280])
        root.addWidget(splitter)

    def _build_stats(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(0)

        self.card_total = _Card("总交易次数", "--", "#58a6ff")
        self.card_win = _Card("胜率", "--", COLOR_UP)
        self.card_avg = _Card("平均收益", "--", COLOR_YELLOW)
        self.card_profit = _Card("累计盈亏", "--", COLOR_UP)
        self.card_max_gain = _Card("最大盈利", "--", COLOR_UP)
        self.card_max_loss = _Card("最大亏损", "--", COLOR_DOWN)

        cards = [self.card_total, self.card_win, self.card_avg,
                 self.card_profit, self.card_max_gain, self.card_max_loss]
        for i, card in enumerate(cards):
            lay.addWidget(card)
            if i < len(cards) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet("color:#21262d;")
                sep.setFixedHeight(30)
                lay.addWidget(sep)
        return frame

    def _build_table(self) -> QTableWidget:
        headers = ["代码", "名称", "买入价", "卖出价", "持仓量",
                   "买入日期", "卖出日期", "盈亏金额", "盈亏%", "平仓原因"]
        tbl = QTableWidget()
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setSortingEnabled(True)
        widths = [65, 90, 70, 70, 65, 90, 90, 80, 70, 150]
        for i, w in enumerate(widths):
            tbl.setColumnWidth(i, w)
        return tbl

    # ===== 数据加载 =====

    @pyqtSlot()
    def load_data(self):
        try:
            stats = self.db.get_statistics()
            transactions = self.db.get_transactions()
            self._update_stats(stats)
            self._fill_table(transactions)
            self._draw_chart(transactions)
        except Exception as e:
            logger.error(f"加载历史数据失败: {e}")

    def _update_stats(self, stats: dict):
        total = int(stats.get('total_trades') or 0)
        win_rate = float(stats.get('win_rate') or 0)
        avg_ret = float(stats.get('avg_return') or 0)
        total_profit = float(stats.get('total_profit') or 0)
        max_gain = float(stats.get('max_gain') or 0)
        max_loss = float(stats.get('max_loss') or 0)

        self.card_total.set_value(str(total))
        self.card_win.set_value(f"{win_rate:.1f}%",
                                 COLOR_UP if win_rate >= 50 else COLOR_DOWN)
        self.card_avg.set_value(f"{avg_ret:+.2f}%",
                                  COLOR_UP if avg_ret >= 0 else COLOR_DOWN)
        self.card_profit.set_value(f"{total_profit:+,.0f} 元",
                                     COLOR_UP if total_profit >= 0 else COLOR_DOWN)
        self.card_max_gain.set_value(f"+{max_gain:.2f}%", COLOR_UP)
        self.card_max_loss.set_value(f"{max_loss:.2f}%", COLOR_DOWN)

    def _fill_table(self, transactions: list):
        self.tbl.setRowCount(len(transactions))
        for row, t in enumerate(transactions):
            pnl = float(t.get('profit_loss') or 0)
            pct = float(t.get('profit_pct') or 0)
            color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else COLOR_FLAT)

            values = [
                t.get('symbol', ''),
                t.get('name', ''),
                f"{float(t.get('buy_price', 0)):.2f}",
                f"{float(t.get('sell_price', 0)):.2f}",
                str(int(t.get('quantity', 100) or 100)),
                (t.get('buy_date') or '')[:10],
                (t.get('sell_date') or '')[:10],
                f"{pnl:+,.2f}",
                f"{pct:+.2f}%",
                t.get('reason', ''),
            ]
            pnl_cols = {7, 8}
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                if col in pnl_cols:
                    item.setForeground(QColor(color))
                self.tbl.setItem(row, col, item)

    def _draw_chart(self, transactions: list):
        if not transactions:
            self.canvas.clear()
            return
        # 按时间排序，计算累计盈亏
        sorted_t = sorted(transactions,
                          key=lambda x: x.get('sell_date') or x.get('created_at') or '')
        cumulative = []
        total = 0
        for t in sorted_t:
            total += float(t.get('profit_loss') or 0)
            cumulative.append(total)
        self.canvas.draw_equity(cumulative)


# ===== 权益曲线画布 =====

class _EquityCanvas(FigureCanvas):
    def __init__(self):
        fig = Figure(figsize=(8, 3), facecolor='#0d1117')
        super().__init__(fig)
        self.fig = fig
        self.ax = None

    def clear(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111, facecolor='#0d1117')
        ax.text(0.5, 0.5, '暂无交易数据',
                transform=ax.transAxes, ha='center', va='center',
                color='#484f58', fontsize=14)
        ax.set_axis_off()
        self.draw()

    def draw_equity(self, cumulative: list):
        try:
            self._do_draw(cumulative)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"权益曲线绘制失败: {e}")
            self.clear()

    def _do_draw(self, cumulative: list):
        self.fig.clear()
        ax = self.fig.add_subplot(111, facecolor='#161b22')
        self.ax = ax

        x = list(range(1, len(cumulative) + 1))
        y = cumulative

        # 颜色
        final = y[-1] if y else 0
        line_color = '#f85149' if final >= 0 else '#3fb950'
        fill_alpha = 0.15

        ax.plot(x, y, color=line_color, linewidth=1.8, zorder=3)
        ax.fill_between(x, y, 0, alpha=fill_alpha, color=line_color)
        ax.axhline(0, color='#484f58', linewidth=0.8, linestyle='--')

        # 标注最终值
        if y:
            sign = '+' if final >= 0 else ''
            ax.annotate(f"{sign}{final:,.0f} 元",
                        xy=(x[-1], y[-1]),
                        xytext=(-10, 10),
                        textcoords='offset points',
                        color=line_color,
                        fontsize=10,
                        ha='right')

        ax.set_facecolor('#161b22')
        ax.tick_params(colors='#8b949e', labelsize=10)
        ax.spines['bottom'].set_color('#21262d')
        ax.spines['left'].set_color('#21262d')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_xlabel("交易次数", color='#8b949e', fontsize=10)
        ax.set_ylabel("累计盈亏 (元)", color='#8b949e', fontsize=10)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda v, _: f"{v:,.0f}"))
        ax.grid(True, color='#21262d', linewidth=0.5, linestyle='-', alpha=0.5)
        self.fig.patch.set_facecolor('#0d1117')
        try:
            self.fig.tight_layout(pad=1.5)
        except Exception:
            pass
        self.draw()


# ===== 统计卡片 =====

class _Card(QWidget):
    def __init__(self, title: str, value: str, color: str = "#e6edf3"):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setAlignment(Qt.AlignCenter)
        self._lbl = QLabel(value)
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setStyleSheet(
            f"font-size:18px;font-weight:bold;color:{color};background:transparent;")
        lbl_t = QLabel(title)
        lbl_t.setAlignment(Qt.AlignCenter)
        lbl_t.setStyleSheet("font-size:11px;color:#8b949e;background:transparent;")
        lay.addWidget(self._lbl)
        lay.addWidget(lbl_t)

    def set_value(self, v: str, color: str = "#e6edf3"):
        self._lbl.setText(v)
        self._lbl.setStyleSheet(
            f"font-size:18px;font-weight:bold;color:{color};background:transparent;")


COLOR_FLAT = "#8b949e"
