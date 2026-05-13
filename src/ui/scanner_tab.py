"""
股票扫描标签页
支持两种模式：
  1. 自选股扫描  —— 对用户手动维护的自选股列表做深度分析
  2. 全市场自动选股 —— 自动从全部 A 股中筛选，无需手动添加
"""
import logging

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QTabWidget,
)

from .styles import (
    COLOR_UP, COLOR_DOWN, COLOR_YELLOW, COLOR_FLAT, COLOR_BLUE,
    REC_COLORS, REC_TEXTS, MACD_TEXTS, change_color, score_color, stars,
)

logger = logging.getLogger(__name__)


# =====================================================================
# 工作线程：全市场自动选股
# =====================================================================

class AutoScreenWorker(QThread):
    """
    尾盘选股线程（次日冲高卖出策略）
    Step1: 全量行情 → Step2: 尾盘预筛（涨2-7%+量比+换手率）
    Step3: 逐只深度分析（均线+MACD+技术形态）→ Step4: 精选10只
    """
    progress = pyqtSignal(int, str)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, config: dict, top_n: int = 10):
        super().__init__()
        self.config = config
        self.top_n = min(top_n, 10)   # 固定最多10只，精而不多
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        import time
        import pandas as pd

        try:
            from src.data.data_fetcher import DataFetcher
            from src.strategy.signal_engine import SignalEngine
            from src.strategy.auto_screener import (
                pre_filter, select_candidates, final_select,
                DEFAULT_PRE_FILTER
            )
        except Exception as e:
            self.error.emit(f"模块加载失败: {e}")
            return

        fetcher = DataFetcher()
        engine = SignalEngine(self.config)

        # ---- Step 1: 拉取全量行情（最多重试 3 次）----
        self.progress.emit(3, "正在连接数据源，拉取全市场行情（约5000只）…")
        all_df = pd.DataFrame()

        for attempt in range(3):
            if not self._running:
                return
            self.progress.emit(3 + attempt * 4,
                f"行情获取中，第 {attempt+1}/3 次尝试…")
            try:
                all_df = fetcher.get_realtime_quotes()
                if not all_df.empty:
                    break
            except Exception as e:
                logger.warning(f"行情第 {attempt+1} 次失败: {e}")
            if attempt < 2:
                time.sleep(3)

        if not self._running:
            return

        if all_df.empty:
            self.error.emit(
                "获取全市场行情失败\n\n"
                "可能原因：\n"
                "• 网络连接不稳定，请检查后重试\n"
                "• 非交易日/非交易时间，数据可能延迟\n"
                "• 数据源暂时维护，稍后再试"
            )
            return

        self.progress.emit(18, f"已获取 {len(all_df)} 只 A 股，正在尾盘条件预筛（涨2-7%+量比+换手率）…")

        # ---- Step 2: 尾盘策略预筛 ----
        try:
            cfg_pre = {**DEFAULT_PRE_FILTER, **self.config.get('pre_filter', {})}
            filtered = pre_filter(all_df, cfg_pre)
            if filtered.empty:
                self.error.emit(
                    "尾盘预筛结果为空\n\n"
                    "可能原因：\n"
                    "• 当前时间不在交易时段，实时涨幅数据为0\n"
                    "• 今日大盘普跌，无符合涨幅2-7%条件的股票\n"
                    "• 建议在下午2:30后运行效果最佳"
                )
                return
            # 尾盘快速评分后取80只进深度分析
            candidates = select_candidates(filtered, 80)
        except Exception as e:
            logger.exception(f"预筛异常: {e}")
            self.error.emit(f"预筛步骤出错: {e}")
            return

        total = len(candidates)
        ok_count = 0
        fail_count = 0
        self.progress.emit(22, f"尾盘预筛完成，{total}只候选进入深度技术分析（均线+MACD+形态）…")

        # ---- Step 3: 逐只深度分析（每只完全隔离）----
        results = []
        for idx, (_, row) in enumerate(candidates.iterrows()):
            if not self._running:
                break

            symbol = str(row.get('symbol', '')).strip()
            name = str(row.get('name', symbol)).strip()

            if not symbol:
                continue

            pct = int(22 + (idx + 1) / total * 73)
            self.progress.emit(pct, f"[{idx+1}/{total}] 分析 {name}({symbol})…")

            # 每只股票完全在 try/except 里，任何异常都不会影响外层
            try:
                quote = {k: v for k, v in row.to_dict().items()
                         if v is not None and str(v) not in ('nan', 'None', '')}

                hist_df = fetcher.get_historical_data(symbol, days=120)

                result = engine.analyze(symbol, name, quote, hist_df)
                if result and isinstance(result, dict):
                    result.pop('_tech', None)
                    # 确保所有 float 值都是可序列化的
                    result = _sanitize_result(result)
                    results.append(result)
                    self.result_ready.emit(result)
                    ok_count += 1
            except Exception as e:
                fail_count += 1
                logger.debug(f"分析 {symbol} 跳过: {type(e).__name__}: {e}")

        if not self._running:
            self.finished.emit(results)
            return

        # ---- Step 4: 精选最终 10 只（严格门槛 + 价值排序）----
        try:
            final = final_select(results)
        except Exception as e:
            logger.warning(f"final_select 异常，直接用原结果: {e}")
            from src.ui.scanner_tab import _buy_value_score
            results.sort(key=_buy_value_score, reverse=True)
            final = results[:10]

        summary = (f"尾盘选股完成 ✓  深度分析 {ok_count} 只  精选出 {len(final)} 只尾盘强势股"
                   f"  (跳过 {fail_count} 只数据不足)")
        self.progress.emit(100, summary)
        self.finished.emit(final)


# =====================================================================
# 工作线程：自选股扫描
# =====================================================================


class WatchlistScanWorker(QThread):
    progress = pyqtSignal(int, str)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, symbols_names: list, config: dict):
        super().__init__()
        self.symbols_names = symbols_names
        self.config = config
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        from src.data.data_fetcher import DataFetcher
        from src.strategy.signal_engine import SignalEngine

        fetcher = DataFetcher()
        engine = SignalEngine(self.config)
        results = []
        total = len(self.symbols_names)

        try:
            all_syms = [s for s, _ in self.symbols_names]
            self.progress.emit(5, "正在获取实时行情…")
            quotes_df = fetcher.get_realtime_quotes(all_syms)

            for idx, (symbol, name) in enumerate(self.symbols_names):
                if not self._running:
                    break
                pct = int((idx + 1) / total * 90) + 5
                self.progress.emit(pct, f"分析 {name}({symbol})…")
                try:
                    if not quotes_df.empty and 'symbol' in quotes_df.columns:
                        row = quotes_df[quotes_df['symbol'] == symbol]
                        quote = row.iloc[0].to_dict() if not row.empty else {}
                    else:
                        quote = fetcher.get_quote(symbol)
                    if not quote or not quote.get('price'):
                        continue
                    hist_df = fetcher.get_historical_data(symbol, days=130)
                    result = engine.analyze(symbol, name, quote, hist_df)
                    if result:
                        result.pop('_tech', None)
                        results.append(result)
                        self.result_ready.emit(result)
                except Exception as e:
                    logger.warning(f"分析 {symbol} 失败: {e}")

            self.progress.emit(98, "保存结果…")
            self.finished.emit(results)
            self.progress.emit(100, "扫描完成")
        except Exception as e:
            self.error.emit(str(e))


# =====================================================================
# 添加自选股对话框
# =====================================================================

class AddStockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自选股")
        self.setFixedSize(400, 190)
        self._fetcher = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edit_symbol = QLineEdit()
        self.edit_symbol.setPlaceholderText("6 位代码，如 600519")
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("自动识别，或手动填写")
        form.addRow("股票代码：", self.edit_symbol)
        form.addRow("股票名称：", self.edit_name)
        lay.addLayout(form)
        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color:#8b949e;font-size:12px;")
        lay.addWidget(self.lbl_hint)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.edit_symbol.textChanged.connect(self._lookup)

    def _lookup(self, text):
        text = text.strip()
        if len(text) == 6 and text.isdigit() and not self.edit_name.text():
            try:
                from src.data.data_fetcher import DataFetcher
                if not self._fetcher:
                    self._fetcher = DataFetcher()
                n = self._fetcher.get_stock_name(text)
                if n != text:
                    self.edit_name.setText(n)
                    self.lbl_hint.setText(f"已识别：{n}")
            except Exception:
                pass

    def _on_ok(self):
        s = self.edit_symbol.text().strip()
        if not s or not s.isdigit() or len(s) != 6:
            QMessageBox.warning(self, "提示", "请输入 6 位数字代码")
            return
        self.accept()

    def get_data(self):
        return self.edit_symbol.text().strip(), self.edit_name.text().strip()


# =====================================================================
# 结果表格（共用）
# =====================================================================

# 列索引常量，方便引用
_COL_RANK   = 0
_COL_SYMBOL = 1
_COL_NAME   = 2
_COL_PRICE  = 3
_COL_CHG    = 4
_COL_FUND   = 5
_COL_TECH   = 6
_COL_TOTAL  = 7
_COL_REC    = 8
_COL_STARS  = 9
_COL_MA20   = 10
_COL_MA60   = 11
_COL_MACD   = 12
_COL_RSI    = 13
_COL_VR     = 14
_COL_PE     = 15

_RESULT_HEADERS = [
    "排名", "代码", "名称", "现价", "涨跌%",
    "基本面", "技术面", "综合分", "建议", "买入价值",
    "MA20", "MA60", "MACD信号", "RSI", "量比", "PE"
]
_RESULT_WIDTHS  = [45, 65, 90, 68, 62, 60, 60, 65, 75, 90, 75, 75, 80, 52, 52, 62]


def _buy_value_score(r: dict) -> float:
    """
    综合"买入价值分"（0-100），决定最终排名顺序
    比 total_score 更看重信号质量和操作性
    """
    total   = float(r.get('total_score') or 0)
    f_score = float(r.get('fundamental_score') or 0)
    t_score = float(r.get('technical_score') or 0)
    rec     = r.get('recommendation', 'hold')
    macd    = r.get('macd_signal', 'neutral')
    rsi     = r.get('rsi')
    vr      = r.get('volume_ratio')
    pe      = r.get('pe_ratio')

    score = total * 0.55 + f_score * 0.20 + t_score * 0.25

    # 建议等级加权
    rec_bonus = {'strong_buy': 18, 'buy': 10, 'hold': 0, 'sell': -10, 'strong_sell': -20}
    score += rec_bonus.get(rec, 0)

    # MACD 金叉重要信号
    if macd == 'golden_cross':
        score += 12
    elif macd == 'bullish':
        score += 5
    elif macd == 'dead_cross':
        score -= 12
    elif macd == 'bearish':
        score -= 5

    # RSI 处于最佳区间（40-65 上升趋势确认）
    if rsi is not None:
        try:
            r_val = float(rsi)
            if 40 <= r_val <= 65:
                score += 8
            elif r_val < 30:
                score += 4   # 超卖反弹机会
            elif r_val > 75:
                score -= 8   # 超买风险
        except (TypeError, ValueError):
            pass

    # 量比适度放大（成交量确认）
    if vr is not None:
        try:
            v_val = float(vr)
            if 1.5 <= v_val <= 3.0:
                score += 6
            elif 1.0 <= v_val < 1.5:
                score += 2
            elif v_val > 5.0:
                score -= 4
        except (TypeError, ValueError):
            pass

    # PE 合理区间加分
    if pe is not None:
        try:
            p_val = float(pe)
            if 0 < p_val < 30:
                score += 5
            elif 30 <= p_val <= 60:
                score += 2
            elif p_val > 100 or p_val < 0:
                score -= 5
        except (TypeError, ValueError):
            pass

    return max(0.0, min(100.0, score))


def _stars_text(buy_value: float) -> str:
    """根据买入价值分返回星级文字"""
    if buy_value >= 85:
        return "★★★★★  极佳"
    elif buy_value >= 72:
        return "★★★★☆  优"
    elif buy_value >= 60:
        return "★★★☆☆  良"
    elif buy_value >= 48:
        return "★★☆☆☆  中"
    else:
        return "★☆☆☆☆  弱"


def _stars_color(buy_value: float) -> str:
    if buy_value >= 85:
        return "#f85149"   # 极佳：红
    elif buy_value >= 72:
        return "#e3b341"   # 优：金
    elif buy_value >= 60:
        return "#3fb950"   # 良：绿
    else:
        return "#8b949e"   # 中/弱：灰


def _build_result_table() -> QTableWidget:
    tbl = QTableWidget()
    tbl.setColumnCount(len(_RESULT_HEADERS))
    tbl.setHorizontalHeaderLabels(_RESULT_HEADERS)
    tbl.setAlternatingRowColors(True)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    tbl.horizontalHeader().setStretchLastSection(False)
    tbl.verticalHeader().setVisible(False)
    # 禁用列排序：结果已按买入价值预排好，避免字符串排序导致顺序错乱
    tbl.setSortingEnabled(False)
    for i, w in enumerate(_RESULT_WIDTHS):
        tbl.setColumnWidth(i, w)
    return tbl


def _fill_result_table(tbl: QTableWidget, results: list):
    """
    用已排序的 results 列表重新渲染整张表，返回 (sorted_results, row_map)
    row_map = {symbol: row_index}
    """
    sorted_results = sorted(results, key=_buy_value_score, reverse=True)

    tbl.setRowCount(0)
    row_map = {}
    for rank, r in enumerate(sorted_results, start=1):
        _append_row(tbl, r, rank=rank)
        row_map[str(r.get('symbol', ''))] = rank - 1
    return sorted_results, row_map


def _append_row(tbl: QTableWidget, r: dict, rank: int = 0):
    """追加单行，rank=0 表示实时追加（扫描中），>0 表示最终排名"""
    row = tbl.rowCount()
    tbl.insertRow(row)

    change   = r.get('change_pct') or 0
    f_s      = r.get('fundamental_score') or 0
    t_s      = r.get('technical_score') or 0
    total    = r.get('total_score') or 0
    rec      = r.get('recommendation', 'hold')
    macd_sig = r.get('macd_signal', 'neutral')
    bv       = _buy_value_score(r)

    def fmt(v, d=2):
        try:
            return f"{float(v):.{d}f}" if v is not None else '--'
        except Exception:
            return '--'

    rank_text = f"#{rank}" if rank > 0 else "…"
    values = [
        rank_text,
        r.get('symbol', ''), r.get('name', ''),
        fmt(r.get('price')),
        f"{change:+.2f}%",
        fmt(f_s, 1), fmt(t_s, 1), fmt(total, 1),
        REC_TEXTS.get(rec, rec),
        _stars_text(bv),
        fmt(r.get('ma20')), fmt(r.get('ma60')),
        MACD_TEXTS.get(macd_sig, macd_sig),
        fmt(r.get('rsi'), 1),
        fmt(r.get('volume_ratio'), 2),
        fmt(r.get('pe_ratio'), 1),
    ]
    colors = [
        "#8b949e",   # 排名：灰
        None, None,
        change_color(change), change_color(change),
        score_color(f_s), score_color(t_s), score_color(total),
        REC_COLORS.get(rec, COLOR_FLAT),
        _stars_color(bv),
        None, None,
        COLOR_UP if macd_sig == 'golden_cross' else (COLOR_DOWN if macd_sig == 'dead_cross' else None),
        None, None, None,
    ]
    for col, (val, color) in enumerate(zip(values, colors)):
        item = QTableWidgetItem(str(val))
        item.setTextAlignment(Qt.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        tbl.setItem(row, col, item)


def _save_as_signals(db, results: list):
    """把 buy/strong_buy 结果保存为信号（尾盘策略：目标+4%，止损-4%）"""
    buyable = [r for r in results if r.get('recommendation') in ('strong_buy', 'buy')]
    if not buyable:
        return 0
    config = db.get_config()
    risk = config.get('risk', {})
    # 尾盘超短线策略：止盈4%、止损4%（配置未设置时取新默认值）
    sl = risk.get('stop_loss_pct',   4.0) / 100
    tp = risk.get('take_profit_pct', 4.0) / 100
    for r in buyable:
        price  = r.get('price', 0)
        total  = r.get('total_score', 50)
        # 优先使用信号引擎已计算好的目标价/止损价
        t_price = r.get('target_price') or round(price * (1 + tp), 2)
        s_price = r.get('stop_loss')    or round(price * (1 - sl), 2)
        patterns = '、'.join(r.get('pattern_names', [])) or r.get('reason', '')
        strength = r.get('signal_strength') or max(1, min(5, int(total / 20)))
        db.save_signal({
            **r,
            'signal_type':    'buy',
            'target_price':   t_price,
            'stop_loss':      s_price,
            'signal_strength': strength,
            'reason':          patterns or r.get('reason', '尾盘强势'),
        })
    return len(buyable)


# =====================================================================
# 主标签页
# =====================================================================

class ScannerTab(QWidget):
    scan_completed = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._worker = None
        self._results_cache: list = []
        self._result_row_map: dict = {}
        self._setup_ui()
        self._load_watchlist()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 标题行
        title_row = QHBoxLayout()
        lbl = QLabel("股票扫描分析")
        lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#f0883e;")
        title_row.addWidget(lbl)
        title_row.addStretch()
        root.addLayout(title_row)

        # ---- 全市场自动选股 横幅 ----
        auto_banner = self._build_auto_banner()
        root.addWidget(auto_banner)

        # ---- 左右分割：自选股 | 结果 ----
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：自选股管理
        left = QGroupBox("自选股（可选）")
        left.setToolTip("如需扫描特定股票，可在此添加；也可直接使用上方【全市场自动选股】")
        ll = QVBoxLayout(left)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("＋ 添加")
        self.btn_add.clicked.connect(self._add_stock)
        self.btn_del = QPushButton("— 删除")
        self.btn_del.clicked.connect(self._del_stock)
        btn_scan_watch = QPushButton("扫描自选股")
        btn_scan_watch.clicked.connect(self._scan_watchlist)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_scan_watch)
        ll.addLayout(btn_row)

        self.tbl_watch = QTableWidget()
        self.tbl_watch.setColumnCount(3)
        self.tbl_watch.setHorizontalHeaderLabels(["代码", "名称", "加入日期"])
        self.tbl_watch.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_watch.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_watch.horizontalHeader().setStretchLastSection(True)
        self.tbl_watch.verticalHeader().setVisible(False)
        self.tbl_watch.setColumnWidth(0, 70)
        self.tbl_watch.setColumnWidth(1, 90)
        ll.addWidget(self.tbl_watch)

        # 右侧：结果
        right = QGroupBox("扫描结果")
        rl = QVBoxLayout(right)

        res_bar = QHBoxLayout()
        self.lbl_count = QLabel("共 0 条结果")
        self.lbl_count.setStyleSheet("color:#8b949e;font-size:12px;")
        btn_save_sig = QPushButton("💾 保存为信号")
        btn_save_sig.clicked.connect(self._save_signals)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_results)
        res_bar.addWidget(self.lbl_count)
        res_bar.addStretch()
        res_bar.addWidget(btn_save_sig)
        res_bar.addWidget(btn_clear)
        rl.addLayout(res_bar)

        self.tbl_result = _build_result_table()
        self.tbl_result.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_result.customContextMenuRequested.connect(self._show_result_context_menu)
        self.tbl_result.doubleClicked.connect(self._on_result_double_click)
        rl.addWidget(self.tbl_result)


        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 1000])
        root.addWidget(splitter)

        # 进度条（全局，两种模式共用）
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#8b949e;font-size:12px;")
        root.addWidget(self.lbl_status)

    def _build_auto_banner(self) -> QFrame:
        """全市场自动选股横幅"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0d1117, stop:0.5 #1f2a3a, stop:1 #0d1117);
                border: 1px solid #1f6feb;
                border-radius: 8px;
            }
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 12, 20, 12)

        icon = QLabel("🤖")
        icon.setStyleSheet("font-size:28px;background:transparent;")

        desc_lay = QVBoxLayout()
        lbl_title = QLabel("全市场自动选股")
        lbl_title.setStyleSheet(
            "font-size:15px;font-weight:bold;color:#58a6ff;background:transparent;")
        lbl_desc = QLabel(
            "自动从全部 A 股（约5000只）中筛选符合策略的候选股，无需手动添加 · "
            "剔除ST/涨跌停/亏损股 → 快速预筛 TOP-80 → 深度技术分析 → 生成信号"
        )
        lbl_desc.setStyleSheet("color:#8b949e;font-size:12px;background:transparent;")
        desc_lay.addWidget(lbl_title)
        desc_lay.addWidget(lbl_desc)

        self.btn_auto = QPushButton("🚀  立即自动选股")
        self.btn_auto.setObjectName("btnScan")
        self.btn_auto.setMinimumWidth(160)
        self.btn_auto.clicked.connect(self._start_auto_screen)

        self.spin_topn = _create_spinbox(20, 200, 80, "只候选")

        lay.addWidget(icon)
        lay.addLayout(desc_lay)
        lay.addStretch()
        lay.addWidget(QLabel("深度分析数量："))
        lay.addWidget(self.spin_topn)
        lay.addSpacing(10)
        lay.addWidget(self.btn_auto)
        return frame

    # ===== 自选股操作 =====

    def _load_watchlist(self):
        wl = self.db.get_watchlist()
        self.tbl_watch.setRowCount(len(wl))
        for row, item in enumerate(wl):
            self.tbl_watch.setItem(row, 0, _cell(item.get('symbol', '')))
            self.tbl_watch.setItem(row, 1, _cell(item.get('name', '')))
            self.tbl_watch.setItem(row, 2, _cell((item.get('added_date') or '')[:10]))

    def _add_stock(self):
        dlg = AddStockDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            symbol, name = dlg.get_data()
            if not self.db.add_to_watchlist(symbol, name):
                QMessageBox.information(self, "提示", f"{symbol} 已在自选股中")
            self._load_watchlist()

    def _del_stock(self):
        rows = set(i.row() for i in self.tbl_watch.selectedItems())
        if not rows:
            return
        syms = [self.tbl_watch.item(r, 0).text() for r in rows]
        names = [self.tbl_watch.item(r, 1).text() for r in rows]
        if QMessageBox.question(
                self, "确认删除", f"删除自选股：{', '.join(names)} ？",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for s in syms:
                self.db.remove_from_watchlist(s)
            self._load_watchlist()

    # ===== 全市场自动选股 =====

    def _start_auto_screen(self):
        if self._is_running():
            return
        top_n = self.spin_topn.value()
        config = self.db.get_config()
        self._reset_for_scan()
        self.btn_auto.setEnabled(False)
        self.btn_auto.setText("⏳ 选股中…")

        self._worker = AutoScreenWorker(config, top_n=top_n)
        self._connect_worker(self._worker)
        self._worker.start()

    # ===== 自选股扫描 =====

    def _scan_watchlist(self):
        wl = self.db.get_watchlist()
        if not wl:
            QMessageBox.information(self, "提示", "自选股列表为空，请先添加股票")
            return
        if self._is_running():
            return
        syms = [(w['symbol'], w.get('name', w['symbol'])) for w in wl]
        config = self.db.get_config()
        self._reset_for_scan()
        self._worker = WatchlistScanWorker(syms, config)
        self._connect_worker(self._worker)
        self._worker.start()

    def _connect_worker(self, worker):
        worker.progress.connect(self._on_progress)
        worker.result_ready.connect(self._on_single_result)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)

    def _is_running(self) -> bool:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在扫描中，请稍候…")
            return True
        return False

    def _reset_for_scan(self):
        self._results_cache = []
        self.tbl_result.setRowCount(0)
        self.lbl_count.setText("正在扫描…")
        self.progress.setValue(0)
        self.progress.setVisible(True)

    # ===== 信号槽 =====

    @pyqtSlot(int, str)
    def _on_progress(self, pct, msg):
        self.progress.setValue(pct)
        self.lbl_status.setText(msg)

    @pyqtSlot(dict)
    def _on_single_result(self, result):
        self._results_cache.append(result)
        _append_row(self.tbl_result, result, rank=0)
        self.lbl_count.setText(f"深度分析中… 已通过 {len(self._results_cache)} 只，精选门槛结束后输出最终10只")

    @pyqtSlot(list)
    def _on_finished(self, results):
        self.progress.setVisible(False)
        self.btn_auto.setEnabled(True)
        self.btn_auto.setText("🚀  立即自动选股")

        if not results:
            self.lbl_count.setText("未发现符合条件的股票")
            return

        # ---- 按买入价值分重新排列并重建表格 ----
        sorted_results, row_map = _fill_result_table(self.tbl_result, results)
        self._results_cache = sorted_results
        self._result_row_map = row_map

        count   = len(sorted_results)
        buy_cnt = sum(1 for r in sorted_results if r.get('recommendation') in ('strong_buy', 'buy'))

        # 取前3名展示
        top3 = "  |  ".join(
            f"#{i+1} {r.get('name','?')}({r.get('symbol','?')}) {_buy_value_score(r):.0f}分"
            for i, r in enumerate(sorted_results[:3])
        )
        self.lbl_count.setText(
            f"共 {count} 只 | 建议买入 {buy_cnt} 只 | "
            f"前三名：{top3}"
        )
        self.lbl_status.setText(
            f"✅ 已按【买入价值】从高到低排序  —  "
            f"总计 {count} 只 | 买入级别 {buy_cnt} 只 | "
            "双击/右键可加入自选股"
        )

        # 清除今日旧信号 → 保存新信号 → 刷新看板
        try:
            self.db.save_scan_results(sorted_results)
            self.db.clear_today_signals()          # 先清空当日旧记录
            saved = _save_as_signals(self.db, sorted_results)
            hint = f"  ✓ 已写入 {saved} 条买入信号到看板" if saved else "  （无强烈买入信号）"
            self.lbl_status.setText(self.lbl_status.text() + hint)
            self.scan_completed.emit()             # 无论是否有信号都刷新看板
        except Exception as e:
            logger.warning(f"保存结果失败: {e}")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.progress.setVisible(False)
        self.btn_auto.setEnabled(True)
        self.btn_auto.setText("🚀  立即自动选股")
        self.lbl_status.setText(f"错误：{msg}")
        QMessageBox.warning(self, "扫描出错", f"扫描过程中发生错误：\n{msg}")

    # ===== 结果操作 =====

    def _save_signals(self):
        if not self._results_cache:
            QMessageBox.information(self, "提示", "请先运行扫描")
            return
        saved = _save_as_signals(self.db, self._results_cache)
        if saved:
            QMessageBox.information(self, "保存成功",
                f"已将 {saved} 只股票的买入信号保存到信号看板")
            self.scan_completed.emit()
        else:
            QMessageBox.information(self, "提示", "当前结果中没有达到买入条件的股票")

    def _clear_results(self):
        self.tbl_result.setRowCount(0)
        self._results_cache = []
        self.lbl_count.setText("共 0 条结果")
        self.lbl_status.setText("")

    def _get_selected_result(self):
        """获取当前选中行对应的结果数据"""
        rows = self.tbl_result.selectedItems()
        if not rows:
            return None
        row_idx = rows[0].row()
        # symbol 现在在第 1 列（第 0 列是排名）
        symbol_item = self.tbl_result.item(row_idx, _COL_SYMBOL)
        if not symbol_item:
            return None
        symbol = symbol_item.text()
        for r in self._results_cache:
            if r.get('symbol') == symbol:
                return r
        return None

    def _show_result_context_menu(self, pos):
        from PyQt5.QtWidgets import QMenu
        result = self._get_selected_result()
        if not result:
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#161b22; color:#e6edf3; border:1px solid #30363d; }
            QMenu::item:selected { background:#21262d; }
        """)
        name = result.get('name', '')
        symbol = result.get('symbol', '')
        act_add = menu.addAction(f"＋  加入自选股  {name}({symbol})")
        act_add.triggered.connect(lambda: self._quick_add_watch(result))
        menu.exec_(self.tbl_result.viewport().mapToGlobal(pos))

    def _on_result_double_click(self, index):
        result = self._get_selected_result()
        if result:
            self._quick_add_watch(result)

    def _quick_add_watch(self, result: dict):
        symbol = result.get('symbol', '')
        name = result.get('name', '')
        if self.db.add_to_watchlist(symbol, name):
            self._load_watchlist()
            self.lbl_status.setText(f"已将 {name}({symbol}) 加入自选股")
        else:
            self.lbl_status.setText(f"{name}({symbol}) 已在自选股中")

    # ===== 外部调用：自动触发 =====

    def trigger_auto_screen(self):
        """供外部（如主窗口启动时）调用，自动开始全市场选股"""
        if not self._is_running():
            self._start_auto_screen()


# =====================================================================
# 工具函数
# =====================================================================

def _sanitize_result(r: dict) -> dict:
    """将结果中的 NaN/inf 替换为 None，防止 Qt 序列化崩溃"""
    import math
    clean = {}
    for k, v in r.items():
        if isinstance(v, float):
            clean[k] = None if (math.isnan(v) or math.isinf(v)) else v
        else:
            clean[k] = v
    return clean


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(Qt.AlignCenter)
    return item


def _create_spinbox(min_val, max_val, default, suffix=''):
    from PyQt5.QtWidgets import QSpinBox
    sb = QSpinBox()
    sb.setRange(min_val, max_val)
    sb.setValue(default)
    if suffix:
        sb.setSuffix(f'  {suffix}')
    sb.setFixedWidth(120)
    return sb
