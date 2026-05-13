"""
持仓管理标签页
支持添加/编辑/平仓持仓，实时更新浮盈浮亏，检测止盈止损预警
"""
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .styles import (
    COLOR_UP, COLOR_DOWN, COLOR_YELLOW, COLOR_FLAT, score_color
)

logger = logging.getLogger(__name__)


# ===== 刷新价格线程 =====

class PriceRefreshWorker(QThread):
    prices_ready = pyqtSignal(dict)  # {symbol: price}

    def __init__(self, symbols: list):
        super().__init__()
        self.symbols = symbols

    def run(self):
        try:
            from src.data.data_fetcher import DataFetcher
            fetcher = DataFetcher()
            df = fetcher.get_realtime_quotes(self.symbols)
            prices = {}
            if not df.empty and 'symbol' in df.columns:
                for _, row in df.iterrows():
                    sym = str(row.get('symbol', ''))
                    price = row.get('price')
                    if sym and price:
                        prices[sym] = float(price)
            self.prices_ready.emit(prices)
        except Exception as e:
            logger.warning(f"刷新价格失败: {e}")
            self.prices_ready.emit({})


# ===== 添加/编辑持仓对话框 =====

class PositionDialog(QDialog):
    def __init__(self, parent=None, position: dict = None):
        super().__init__(parent)
        self.position = position or {}
        self.setWindowTitle("编辑持仓" if position else "添加持仓")
        self.setFixedSize(420, 380)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.edit_symbol = QLineEdit(self.position.get('symbol', ''))
        self.edit_symbol.setPlaceholderText("6位代码，如 600519")
        self.edit_name = QLineEdit(self.position.get('name', ''))
        self.edit_name.setPlaceholderText("股票名称（可自动识别）")

        self.spin_buy = QDoubleSpinBox()
        self.spin_buy.setRange(0.01, 99999)
        self.spin_buy.setDecimals(2)
        self.spin_buy.setSuffix(" 元")
        self.spin_buy.setValue(float(self.position.get('buy_price', 10)))

        self.spin_qty = QSpinBox()
        self.spin_qty.setRange(100, 9999999)
        self.spin_qty.setSingleStep(100)
        self.spin_qty.setSuffix(" 股")
        self.spin_qty.setValue(int(self.position.get('quantity', 100)))

        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0, 99999)
        self.spin_target.setDecimals(2)
        self.spin_target.setSuffix(" 元")
        self.spin_target.setSpecialValueText("不设置")
        target = self.position.get('target_price') or 0
        self.spin_target.setValue(float(target))

        self.spin_stop = QDoubleSpinBox()
        self.spin_stop.setRange(0, 99999)
        self.spin_stop.setDecimals(2)
        self.spin_stop.setSuffix(" 元")
        self.spin_stop.setSpecialValueText("不设置")
        stop = self.position.get('stop_loss') or 0
        self.spin_stop.setValue(float(stop))

        self.edit_date = QLineEdit(
            self.position.get('buy_date', datetime.now().strftime('%Y-%m-%d'))
        )
        self.edit_notes = QLineEdit(self.position.get('notes', ''))

        form.addRow("股票代码：", self.edit_symbol)
        form.addRow("股票名称：", self.edit_name)
        form.addRow("买入价格：", self.spin_buy)
        form.addRow("持仓数量：", self.spin_qty)
        form.addRow("目标价位：", self.spin_target)
        form.addRow("止损价位：", self.spin_stop)
        form.addRow("买入日期：", self.edit_date)
        form.addRow("备注：", self.edit_notes)
        lay.addLayout(form)

        # 快速计算止损提示
        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color:#8b949e;font-size:11px;")
        lay.addWidget(self.lbl_hint)
        self.spin_buy.valueChanged.connect(self._calc_hint)
        self._calc_hint()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # 自动识别名称
        self.edit_symbol.textChanged.connect(self._lookup_name)

    def _lookup_name(self, text):
        text = text.strip()
        if len(text) == 6 and text.isdigit() and not self.edit_name.text():
            try:
                from src.data.data_fetcher import DataFetcher
                name = DataFetcher().get_stock_name(text)
                if name != text:
                    self.edit_name.setText(name)
            except Exception:
                pass

    def _calc_hint(self):
        buy = self.spin_buy.value()
        stop8 = round(buy * 0.92, 2)
        target20 = round(buy * 1.20, 2)
        self.lbl_hint.setText(f"参考：止损(8%) = {stop8}  目标(20%) = {target20}")

    def _on_ok(self):
        symbol = self.edit_symbol.text().strip()
        if not symbol:
            QMessageBox.warning(self, "提示", "请输入股票代码")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            'symbol': self.edit_symbol.text().strip(),
            'name': self.edit_name.text().strip() or self.edit_symbol.text().strip(),
            'buy_price': self.spin_buy.value(),
            'quantity': self.spin_qty.value(),
            'target_price': self.spin_target.value() or None,
            'stop_loss': self.spin_stop.value() or None,
            'buy_date': self.edit_date.text().strip() or datetime.now().strftime('%Y-%m-%d'),
            'notes': self.edit_notes.text().strip(),
        }


# ===== 平仓对话框 =====

class ClosePositionDialog(QDialog):
    def __init__(self, position: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"平仓 {position.get('name', '')}({position.get('symbol', '')})")
        self.setFixedSize(360, 220)
        self.position = position
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_sell = QDoubleSpinBox()
        self.spin_sell.setRange(0.01, 99999)
        self.spin_sell.setDecimals(2)
        self.spin_sell.setSuffix(" 元")
        self.spin_sell.setValue(float(self.position.get('buy_price', 10)))

        buy = float(self.position.get('buy_price', 0))
        sell = self.spin_sell.value()
        self.lbl_pnl = QLabel()
        self.lbl_pnl.setStyleSheet("font-weight:bold;")

        self.edit_reason = QLineEdit()
        self.edit_reason.setPlaceholderText("如：止盈 / 止损 / 策略信号")

        form.addRow("卖出价格：", self.spin_sell)
        form.addRow("盈亏预览：", self.lbl_pnl)
        form.addRow("平仓原因：", self.edit_reason)
        lay.addLayout(form)

        self.spin_sell.valueChanged.connect(self._update_pnl)
        self._update_pnl()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _update_pnl(self):
        sell = self.spin_sell.value()
        buy = float(self.position.get('buy_price', sell))
        qty = float(self.position.get('quantity', 100))
        pnl = (sell - buy) * qty
        pct = (sell - buy) / buy * 100 if buy else 0
        color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else COLOR_FLAT)
        sign = '+' if pct >= 0 else ''
        self.lbl_pnl.setText(f"{sign}{pct:.2f}%  ({sign}{pnl:.2f} 元)")
        self.lbl_pnl.setStyleSheet(f"font-weight:bold;color:{color};background:transparent;")

    def get_data(self):
        return self.spin_sell.value(), self.edit_reason.text().strip()


# ===== 主标签页 =====

class PortfolioTab(QWidget):
    position_changed = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._current_prices: dict = {}
        self._refresh_worker = None
        self._setup_ui()
        self.load_portfolio()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        lbl = QLabel("我的持仓")
        lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#f0883e;")

        self.btn_add = QPushButton("＋ 新增持仓")
        self.btn_add.setObjectName("btnBuy")
        self.btn_add.clicked.connect(self._add_position)

        self.btn_edit = QPushButton("编辑")
        self.btn_edit.clicked.connect(self._edit_position)

        self.btn_close = QPushButton("平仓")
        self.btn_close.setObjectName("btnSell")
        self.btn_close.clicked.connect(self._close_position)

        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("btnDanger")
        self.btn_del.clicked.connect(self._delete_position)

        self.btn_refresh = QPushButton("刷新价格")
        self.btn_refresh.clicked.connect(self.refresh_prices)

        toolbar.addWidget(lbl)
        toolbar.addStretch()
        for b in [self.btn_add, self.btn_edit, self.btn_close,
                  self.btn_del, self.btn_refresh]:
            toolbar.addWidget(b)
        root.addLayout(toolbar)

        # 汇总卡片
        root.addWidget(self._build_summary())

        # 持仓表格
        self.tbl = self._build_table()
        root.addWidget(self.tbl)

    def _build_summary(self) -> QWidget:
        frame = QWidget()
        frame.setStyleSheet("""
            QWidget {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 10, 20, 10)

        self.lbl_positions = _stat("持仓数量", "0 只")
        self.lbl_cost = _stat("总成本", "0 元")
        self.lbl_value = _stat("当前市值", "0 元")
        self.lbl_pnl = _stat("总浮盈亏", "0 元")
        self.lbl_pnl_pct = _stat("收益率", "0%")

        for w in [self.lbl_positions, self.lbl_cost, self.lbl_value,
                  self.lbl_pnl, self.lbl_pnl_pct]:
            lay.addWidget(w)
        return frame

    def _build_table(self) -> QTableWidget:
        headers = ["代码", "名称", "买入价", "持仓量", "成本",
                   "现价", "市值", "浮盈亏", "浮盈%",
                   "目标价", "止损价", "距目标%", "距止损%",
                   "买入日期", "状态"]
        tbl = QTableWidget()
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        widths = [65, 90, 72, 65, 80, 72, 80, 80, 65, 72, 72, 72, 72, 90, 80]
        for i, w in enumerate(widths):
            tbl.setColumnWidth(i, w)
        return tbl

    # ===== 数据加载 =====

    def load_portfolio(self):
        positions = self.db.get_portfolio()
        self._fill_table(positions)
        self._update_summary(positions)

    def _fill_table(self, positions: list):
        self.tbl.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            try:
                self._fill_row(row, pos)
            except Exception as e:
                logger.warning(f"持仓行渲染失败: {e}")

    def _fill_row(self, row: int, pos: dict):
        buy_price = float(pos.get('buy_price') or 0)
        qty = float(pos.get('quantity') or 100)
        cost = buy_price * qty
        symbol = pos.get('symbol', '')
        cur_price = self._current_prices.get(symbol, buy_price)
        if not cur_price:
            cur_price = buy_price
        market_val = cur_price * qty
        pnl = market_val - cost
        pnl_pct = (pnl / cost * 100) if cost else 0

        target = pos.get('target_price')
        stop = pos.get('stop_loss')
        to_target = ((target - cur_price) / cur_price * 100) if (target and cur_price) else None
        to_stop = ((cur_price - stop) / cur_price * 100) if (stop and cur_price) else None

        status_text = "持有"
        status_color = "#8b949e"
        if stop and cur_price <= stop:
            status_text = "⚠ 触及止损"
            status_color = COLOR_DOWN
        elif stop and cur_price <= stop * 1.03:
            status_text = "⚠ 接近止损"
            status_color = COLOR_YELLOW
        elif target and cur_price >= target:
            status_text = "✓ 达到目标"
            status_color = COLOR_UP
        elif pnl_pct >= 15:
            status_text = "↑ 高浮盈"
            status_color = COLOR_UP

        def fmt(v, dec=2):
            try:
                return f"{float(v):.{dec}f}" if v is not None else '--'
            except Exception:
                return '--'

        values = [
            symbol,
            pos.get('name', ''),
            fmt(buy_price),
            f"{int(qty)}",
            fmt(cost),
            fmt(cur_price),
            fmt(market_val),
            fmt(pnl),
            f"{pnl_pct:+.2f}%",
            fmt(target) if target else '--',
            fmt(stop) if stop else '--',
            f"{to_target:+.1f}%" if to_target is not None else '--',
            f"{to_stop:.1f}%" if to_stop is not None else '--',
            (pos.get('buy_date') or '')[:10],
            status_text,
        ]
        v_colors = [
            None, None, None, None, None,
            change_color_by_pnl(pnl_pct),
            None,
            change_color_by_pnl(pnl_pct),
            change_color_by_pnl(pnl_pct),
            COLOR_UP, COLOR_DOWN,
            change_color_by_pnl(to_target) if to_target is not None else None,
            COLOR_DOWN if to_stop is not None and to_stop < 3 else None,
            None, status_color,
        ]
        for col, (val, color) in enumerate(zip(values, v_colors)):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, pos.get('id'))
            if color:
                item.setForeground(QColor(color))
            self.tbl.setItem(row, col, item)

    def _update_summary(self, positions: list):
        total_cost = 0
        total_val = 0
        for pos in positions:
            buy = float(pos.get('buy_price', 0))
            qty = float(pos.get('quantity', 100))
            sym = pos.get('symbol', '')
            cur = self._current_prices.get(sym, buy)
            total_cost += buy * qty
            total_val += cur * qty

        pnl = total_val - total_cost
        pnl_pct = pnl / total_cost * 100 if total_cost else 0
        color = change_color_by_pnl(pnl_pct)

        self.lbl_positions.set_value(f"{len(positions)} 只")
        self.lbl_cost.set_value(f"{total_cost:,.0f} 元")
        self.lbl_value.set_value(f"{total_val:,.0f} 元")
        self.lbl_pnl.set_value(f"{pnl:+,.0f} 元", color)
        self.lbl_pnl_pct.set_value(f"{pnl_pct:+.2f}%", color)

    # ===== 刷新价格 =====

    @pyqtSlot()
    def refresh_prices(self):
        positions = self.db.get_portfolio()
        symbols = [p['symbol'] for p in positions if p.get('symbol')]
        if not symbols:
            return
        if self._refresh_worker and self._refresh_worker.isRunning():
            return
        self._refresh_worker = PriceRefreshWorker(symbols)
        self._refresh_worker.prices_ready.connect(self._on_prices_ready)
        self._refresh_worker.start()

    @pyqtSlot(dict)
    def _on_prices_ready(self, prices: dict):
        self._current_prices.update(prices)
        positions = self.db.get_portfolio()
        self._fill_table(positions)
        self._update_summary(positions)
        self._check_alerts(positions)

    def _check_alerts(self, positions: list):
        from src.strategy.signal_engine import SignalEngine
        engine = SignalEngine(self.db.get_config())
        for pos in positions:
            sym = pos.get('symbol', '')
            cur = self._current_prices.get(sym)
            if not cur:
                continue
            alerts = engine.check_position_alerts(pos, cur)
            for alert in alerts:
                if alert.get('severity') == 'critical':
                    QMessageBox.warning(self, "止损预警！", alert['msg'])

    # ===== 操作 =====

    def _get_selected_id(self):
        rows = self.tbl.selectedItems()
        if not rows:
            return None
        return rows[0].data(Qt.UserRole)

    def _add_position(self):
        dlg = PositionDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            self.db.add_position(data)
            self.load_portfolio()
            self.position_changed.emit()

    def _edit_position(self):
        pid = self._get_selected_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        positions = {p['id']: p for p in self.db.get_portfolio()}
        pos = positions.get(pid)
        if not pos:
            return
        dlg = PositionDialog(self, pos)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            self.db.update_position(pid, data)
            self.load_portfolio()

    def _close_position(self):
        pid = self._get_selected_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        positions = {p['id']: p for p in self.db.get_portfolio()}
        pos = positions.get(pid)
        if not pos:
            return
        dlg = ClosePositionDialog(pos, self)
        if dlg.exec_() == QDialog.Accepted:
            sell_price, reason = dlg.get_data()
            self.db.close_position(pid, sell_price, reason)
            self.load_portfolio()
            self.position_changed.emit()

    def _delete_position(self):
        pid = self._get_selected_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        reply = QMessageBox.question(self, "确认删除",
            "确认删除该持仓记录？（不会生成交易记录）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_position(pid)
            self.load_portfolio()


# ===== 工具 =====

def change_color_by_pnl(pct) -> str:
    try:
        v = float(pct)
        return COLOR_UP if v > 0 else (COLOR_DOWN if v < 0 else COLOR_FLAT)
    except (TypeError, ValueError):
        return COLOR_FLAT


class _stat(QWidget):
    def __init__(self, title: str, value: str):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(2)
        self._lbl_val = QLabel(value)
        self._lbl_val.setAlignment(Qt.AlignCenter)
        self._lbl_val.setStyleSheet("font-size:16px;font-weight:bold;background:transparent;")
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size:11px;color:#8b949e;background:transparent;")
        lay.addWidget(self._lbl_val)
        lay.addWidget(lbl_title)

    def set_value(self, v: str, color: str = "#e6edf3"):
        self._lbl_val.setText(v)
        self._lbl_val.setStyleSheet(
            f"font-size:16px;font-weight:bold;color:{color};background:transparent;"
        )


COLOR_FLAT = "#8b949e"
