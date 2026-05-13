"""
SmartSelect 主窗口 - 单页布局

┌─ Header ─────────────────────────────────────────────────────────────┐
│ 品牌 + 3大指数 + 市场状态 + 时间 + [立即选股] [刷新] [⚙]            │
├─ Body ───────────────────────────────────────────────────────────────┤
│ ┌─ 左侧统计栏 220px ─┐  ┌─ 右侧主区域 ────────────────────────────┐ │
│ │  今日统计卡片       │  │  进度条 / 状态文字                      │ │
│ │  信号摘要列表       │  │  综合信息表格（全字段，横向滚动）        │ │
│ │                     │  ├─ 分割线 ───────────────────────────────┤ │
│ │                     │  │  选中股票详情面板                       │ │
│ └─────────────────────┘  └────────────────────────────────────────┘ │
├─ Status Bar ─────────────────────────────────────────────────────────┤
└──────────────────────────────────────────────────────────────────────┘
"""
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QAction, QMenu,
)

from .styles import (
    DARK_STYLE, COLOR_UP, COLOR_DOWN, COLOR_FLAT, COLOR_ACCENT,
    COLOR_YELLOW, COLOR_BLUE, COLOR_PURPLE,
    REC_COLORS, REC_TEXTS, MACD_TEXTS,
    change_color, score_color, stars,
)

logger = logging.getLogger(__name__)

# ── 结果表列定义 ─────────────────────────────────────────────────────
_COLS = [
    ("排名",    40),
    ("代码",    65),
    ("名称",    92),
    ("现价",    70),
    ("涨跌%",   64),
    ("触发形态", 150),
    ("综合分",  62),
    ("技术分",  58),
    ("建议",    78),
    ("买入价值", 90),
    ("MA20",   68),
    ("MA60",   68),
    ("MACD",   75),
    ("RSI",    50),
    ("量比",    55),
    ("换手率",  60),
    ("PE",     55),
    ("目标价",  70),
    ("止损价",  70),
]
_HEADERS = [c[0] for c in _COLS]
_WIDTHS  = [c[1] for c in _COLS]

# 列索引常量
_C = {h: i for i, h in enumerate(_HEADERS)}


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._worker = None
        self._results: list = []

        self.setWindowTitle("SmartSelect  ·  尾盘选股 + 次日冲高")
        self.setMinimumSize(1280, 760)
        self.resize(1520, 900)
        self.setStyleSheet(DARK_STYLE)

        self._build_ui()
        self._setup_menu()
        self._setup_timers()
        self._load_today_signals()

    # =========================================================
    # UI 构建
    # =========================================================

    def _build_ui(self):
        root_w = QWidget()
        self.setCentralWidget(root_w)
        root = QVBoxLayout(root_w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)

        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("就绪  ·  数据来源：AKShare  ·  本软件仅供学习研究，不构成投资建议")

    # ── 顶部 Header ───────────────────────────────────────────

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(56)
        hdr.setStyleSheet("""
            QFrame#appHeader {
                background: #0d1117;
                border-bottom: 2px solid #f0883e;
            }
        """)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(0)

        # 品牌
        lbl_brand = QLabel("📈 SmartSelect")
        lbl_brand.setStyleSheet(
            "font-size:18px;font-weight:bold;color:#f0883e;"
            "background:transparent;letter-spacing:1px;min-width:170px;")

        # 副标题
        lbl_sub = QLabel("尾盘选股策略")
        lbl_sub.setStyleSheet("font-size:11px;color:#484f58;background:transparent;margin-left:4px;")

        lay.addWidget(lbl_brand)
        lay.addWidget(lbl_sub)
        lay.addStretch()

        # 大盘指数
        self.lbl_sh  = _idx_lbl()
        self.lbl_sz  = _idx_lbl()
        self.lbl_cyb = _idx_lbl()
        for lbl, txt in [(self.lbl_sh, "上证"), (self.lbl_sz, "深证"), (self.lbl_cyb, "创业板")]:
            lbl.setToolTip(txt)
        for w in (self.lbl_sh, _vsep(), self.lbl_sz, _vsep(), self.lbl_cyb, _vsep()):
            lay.addWidget(w)

        # 市场状态
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size:12px;background:transparent;min-width:80px;")
        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet("font-size:12px;color:#484f58;background:transparent;min-width:148px;")

        lay.addWidget(self.lbl_status)
        lay.addWidget(self.lbl_time)
        lay.addWidget(_vsep())

        # 操作按钮
        self.btn_scan = QPushButton("🚀  立即选股")
        self.btn_scan.setObjectName("btnScan")
        self.btn_scan.setFixedHeight(36)
        self.btn_scan.clicked.connect(self._start_scan)

        self.btn_refresh = QPushButton("⟳ 刷新信号")
        self.btn_refresh.setObjectName("btnRefresh")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.clicked.connect(self._load_today_signals)

        btn_settings = QPushButton("⚙")
        btn_settings.setObjectName("btnSettings")
        btn_settings.setFixedSize(32, 32)
        btn_settings.setToolTip("策略参数设置")
        btn_settings.clicked.connect(self._open_settings)

        lay.addSpacing(8)
        lay.addWidget(self.btn_scan)
        lay.addSpacing(6)
        lay.addWidget(self.btn_refresh)
        lay.addSpacing(6)
        lay.addWidget(btn_settings)

        self._refresh_clock()
        return hdr

    # ── 主体区域 ──────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_sidebar())
        lay.addWidget(_vline())
        lay.addWidget(self._build_main_area(), 1)
        return w

    # ── 左侧统计栏 ────────────────────────────────────────────

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("QFrame{background:#0d1117;border:none;}")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(10)

        # ── 选股时机提示 ──
        self.lbl_timing = QLabel()
        self.lbl_timing.setAlignment(Qt.AlignCenter)
        self.lbl_timing.setStyleSheet(
            "font-size:12px;color:#e3b341;background:#1c1a10;"
            "border:1px solid #3d3210;border-radius:6px;padding:6px 8px;")
        self.lbl_timing.setWordWrap(True)
        lay.addWidget(self.lbl_timing)
        self._refresh_timing_hint()

        # ── 今日统计卡片组 ──
        card_frame = QFrame()
        card_frame.setStyleSheet(
            "QFrame{background:#161b22;border:1px solid #21262d;border-radius:8px;}")
        cf = QVBoxLayout(card_frame)
        cf.setContentsMargins(12, 10, 12, 10)
        cf.setSpacing(6)

        lbl_title = QLabel("今日选股统计")
        lbl_title.setStyleSheet("font-size:12px;color:#58a6ff;font-weight:bold;background:transparent;")
        cf.addWidget(lbl_title)

        self._card_total  = _SideCard("精选股票", "—", "#e6edf3")
        self._card_strong = _SideCard("强烈买入 🔥", "—", COLOR_UP)
        self._card_buy    = _SideCard("建议买入 ✅", "—", "#ff7b72")
        self._card_time   = _SideCard("最后选股", "—", "#8b949e")

        for c in [self._card_total, self._card_strong, self._card_buy, self._card_time]:
            cf.addWidget(c)
        lay.addWidget(card_frame)

        # ── 今日信号摘要 ──
        lbl_sig = QLabel("今日买入信号")
        lbl_sig.setStyleSheet("font-size:12px;color:#58a6ff;font-weight:bold;background:transparent;")
        lay.addWidget(lbl_sig)

        self.signal_list = QWidget()
        self.signal_list.setStyleSheet("background:transparent;")
        self._sig_layout = QVBoxLayout(self.signal_list)
        self._sig_layout.setContentsMargins(0, 0, 0, 0)
        self._sig_layout.setSpacing(3)

        scroll = QScrollArea()
        scroll.setWidget(self.signal_list)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:#0d1117;border:1px solid #21262d;border-radius:6px;}"
            "QScrollBar:vertical{width:4px;background:#0d1117;}"
            "QScrollBar::handle:vertical{background:#30363d;border-radius:2px;}")
        lay.addWidget(scroll, 1)

        # 风险提示
        lbl_risk = QLabel("⚠ 14:40–14:55 买入\n次日 9:30–10:30 卖出\n止盈+4% / 止损-4%")
        lbl_risk.setStyleSheet(
            "font-size:11px;color:#484f58;background:#0d1117;"
            "border:1px solid #21262d;border-radius:6px;padding:6px 8px;")
        lbl_risk.setWordWrap(True)
        lay.addWidget(lbl_risk)

        return sidebar

    # ── 右侧主区域 ────────────────────────────────────────────

    def _build_main_area(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0d1117;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # ── 工具栏：标题 + 进度条 + 状态 ──
        tool_row = QHBoxLayout()
        self.lbl_scan_title = QLabel("今日尾盘精选")
        self.lbl_scan_title.setStyleSheet(
            "font-size:15px;font-weight:bold;color:#f0883e;background:transparent;")
        self.lbl_result_info = QLabel("尚未运行选股")
        self.lbl_result_info.setStyleSheet("font-size:12px;color:#8b949e;background:transparent;")
        tool_row.addWidget(self.lbl_scan_title)
        tool_row.addSpacing(12)
        tool_row.addWidget(self.lbl_result_info, 1)
        lay.addLayout(tool_row)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFixedHeight(6)
        self.progress.setVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background:#21262d; border:none; border-radius:3px;
                text-align:center; color:transparent;
            }
            QProgressBar::chunk {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #f0883e, stop:1 #e3b341);
                border-radius:3px;
            }
        """)
        lay.addWidget(self.progress)

        # ── 综合结果表格（垂直拆分：表格 + 详情面板）──
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # 主表格
        self.tbl = self._build_result_table()
        self.tbl.currentCellChanged.connect(self._on_row_changed)
        self.tbl.doubleClicked.connect(self._on_row_changed_by_click)
        splitter.addWidget(self.tbl)

        # 详情面板
        self.detail_panel = self._build_detail_panel()
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([520, 200])
        lay.addWidget(splitter, 1)

        return w

    def _build_result_table(self) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setColumnCount(len(_HEADERS))
        tbl.setHorizontalHeaderLabels(_HEADERS)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSortingEnabled(False)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        tbl.horizontalHeader().setStretchLastSection(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(True)
        tbl.setStyleSheet("""
            QTableWidget {
                background:#0d1117;
                alternate-background-color:#0e1318;
                gridline-color:#1c2028;
                selection-background-color:#1f3a5f;
                font-size:13px;
            }
            QHeaderView::section {
                background:#161b22;
                color:#8b949e;
                padding:7px 4px;
                border:none;
                border-right:1px solid #21262d;
                border-bottom:2px solid #21262d;
                font-size:12px;
                font-weight:bold;
            }
            QTableWidget::item { padding:5px 6px; }
        """)
        for i, w in enumerate(_WIDTHS):
            tbl.setColumnWidth(i, w)
        return tbl

    def _build_detail_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background:#0d1117;
                border-top:2px solid #21262d;
            }
        """)
        panel.setMinimumHeight(160)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(6)

        # 顶部：股票名称 + 基本价格信息
        top = QHBoxLayout()
        self.det_title = QLabel("← 点击上方表格中任意股票行，查看完整详情")
        self.det_title.setStyleSheet(
            "font-size:15px;font-weight:bold;color:#8b949e;background:transparent;")
        self.det_price = QLabel()
        self.det_price.setStyleSheet("font-size:20px;font-weight:bold;background:transparent;")
        self.det_change = QLabel()
        self.det_change.setStyleSheet("font-size:14px;font-weight:bold;background:transparent;")
        self.det_rec = QLabel()
        self.det_rec.setStyleSheet(
            "font-size:13px;font-weight:bold;background:transparent;padding:2px 10px;"
            "border-radius:4px;border:1px solid #30363d;")

        top.addWidget(self.det_title)
        top.addStretch()
        top.addWidget(self.det_change)
        top.addSpacing(8)
        top.addWidget(self.det_price)
        top.addSpacing(16)
        top.addWidget(self.det_rec)
        lay.addLayout(top)

        # 中部：两列详情
        mid = QHBoxLayout()
        mid.setSpacing(24)

        # 左列：核心指标
        self.det_left = QLabel()
        self.det_left.setStyleSheet(
            "font-size:12px;color:#c9d1d9;background:transparent;line-height:160%;")
        self.det_left.setWordWrap(True)

        # 右列：技术指标
        self.det_right = QLabel()
        self.det_right.setStyleSheet(
            "font-size:12px;color:#c9d1d9;background:transparent;line-height:160%;")
        self.det_right.setWordWrap(True)

        # 中间：形态 + 操作提示
        self.det_center = QLabel()
        self.det_center.setStyleSheet(
            "font-size:12px;color:#e3b341;background:#1a1800;"
            "border:1px solid #3d3210;border-radius:6px;"
            "padding:8px 12px;line-height:170%;")
        self.det_center.setWordWrap(True)
        self.det_center.setMinimumWidth(260)

        mid.addWidget(self.det_left, 2)
        mid.addWidget(self.det_center, 3)
        mid.addWidget(self.det_right, 2)
        lay.addLayout(mid)

        return panel

    # =========================================================
    # 数据加载 / 扫描
    # =========================================================

    def _load_today_signals(self):
        """从数据库加载今日信号，填充左栏和主表格"""
        try:
            signals = self.db.get_today_signals()
            buy_sigs = [s for s in signals if s.get('signal_type') == 'buy']
            strong   = [s for s in buy_sigs if s.get('recommendation') == 'strong_buy']

            self._card_total.set_value(str(len(buy_sigs)))
            self._card_strong.set_value(str(len(strong)))
            self._card_buy.set_value(str(len(buy_sigs) - len(strong)))

            if buy_sigs:
                ts = (buy_sigs[0].get('created_at') or '')
                self._card_time.set_value(ts[-8:-3] or "--")

            self._fill_signal_sidebar(buy_sigs)

            # 把信号转成结果格式填充主表格
            if buy_sigs:
                self._fill_table(buy_sigs)
                self.lbl_result_info.setText(
                    f"共 {len(buy_sigs)} 只  |  强烈买入 {len(strong)} 只  |  建议买入 {len(buy_sigs)-len(strong)} 只")
        except Exception as e:
            logger.debug(f"加载今日信号失败: {e}")

    def _fill_signal_sidebar(self, signals: list):
        """左侧今日信号迷你列表"""
        while self._sig_layout.count():
            item = self._sig_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not signals:
            lbl = QLabel("今日暂无信号\n请点击「立即选股」")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size:12px;color:#484f58;background:transparent;padding:10px 0;")
            lbl.setWordWrap(True)
            self._sig_layout.addWidget(lbl)
            return

        for s in signals:
            is_strong = s.get('recommendation') == 'strong_buy'
            w = _SigRow(s, is_strong)
            w.clicked.connect(lambda r=s: self._show_signal_detail(r))
            self._sig_layout.addWidget(w)
        self._sig_layout.addStretch()

    def _fill_table(self, data: list):
        """填充主结果表格"""
        self.tbl.setRowCount(0)
        self._results = list(data)
        self.tbl.setRowCount(len(data))

        for rank, r in enumerate(data, start=1):
            self._set_row(rank - 1, r, rank)

        self.tbl.resizeRowsToContents()

    def _set_row(self, row: int, r: dict, rank: int):
        change  = float(r.get('change_pct') or 0)
        total   = float(r.get('total_score') or 0)
        t_score = float(r.get('technical_score') or r.get('total_score') or 0)
        rec     = r.get('recommendation', 'hold')
        macd    = r.get('macd_signal', 'neutral')
        rsi     = r.get('rsi') or r.get('rsi14')
        vr      = r.get('volume_ratio')
        tr      = r.get('turnover_rate')
        pe      = r.get('pe_ratio')
        ma20    = r.get('ma20')
        ma60    = r.get('ma60')
        price   = float(r.get('price') or 0)
        target  = r.get('target_price')
        stop    = r.get('stop_loss')

        # 形态
        patterns = r.get('pattern_names') or []
        if isinstance(patterns, list):
            pattern_str = '  ·  '.join(patterns) if patterns else (r.get('reason') or '--')
        else:
            pattern_str = str(patterns) or (r.get('reason') or '--')

        # 买入价值星级
        from .scanner_tab import _buy_value_score, _stars_text, _stars_color
        bv = _buy_value_score(r)
        stars_txt   = _stars_text(bv)
        stars_clr   = _stars_color(bv)

        def fmt(v, d=2):
            try:
                return f"{float(v):.{d}f}" if v is not None else '--'
            except Exception:
                return '--'

        rank_is_strong = rec == 'strong_buy'
        row_bg = QColor('#0f1f0f') if rank_is_strong else None

        values = [
            f"#{rank}",
            r.get('symbol', ''),
            ('🔥 ' if rank_is_strong else '') + r.get('name', ''),
            fmt(price),
            f"{change:+.2f}%",
            pattern_str,
            fmt(total, 1),
            fmt(t_score, 1),
            REC_TEXTS.get(rec, rec),
            stars_txt,
            fmt(ma20),
            fmt(ma60),
            MACD_TEXTS.get(macd, macd),
            fmt(rsi, 1),
            fmt(vr, 1) + 'X' if vr is not None else '--',
            (fmt(tr, 1) + '%') if tr is not None else '--',
            fmt(pe, 1),
            fmt(target),
            fmt(stop),
        ]
        fg_overrides = {
            _C["涨跌%"]:  change_color(change),
            _C["综合分"]:  score_color(total),
            _C["技术分"]:  score_color(t_score),
            _C["建议"]:    REC_COLORS.get(rec, COLOR_FLAT),
            _C["买入价值"]: stars_clr,
            _C["MACD"]:   (COLOR_UP if macd == 'golden_cross'
                           else COLOR_DOWN if macd == 'dead_cross'
                           else COLOR_YELLOW if macd == 'bullish' else COLOR_FLAT),
            _C["目标价"]:  COLOR_UP,
            _C["止损价"]:  COLOR_DOWN,
            _C["排名"]:    "#f0883e" if rank <= 3 else "#8b949e",
        }
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(
                Qt.AlignLeft | Qt.AlignVCenter if col in (_C["触发形态"], _C["买入价值"]) else Qt.AlignCenter
            )
            if row_bg:
                item.setBackground(row_bg)
            if col in fg_overrides:
                item.setForeground(QColor(fg_overrides[col]))
            self.tbl.setItem(row, col, item)

        # 行高
        self.tbl.setRowHeight(row, 32)

    # =========================================================
    # 扫描工作线程
    # =========================================================

    def _start_scan(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在扫描中，请稍候…")
            return
        config = self.db.get_config()
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("⏳ 选股中…")
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.lbl_result_info.setText("正在连接数据源…")
        self.tbl.setRowCount(0)
        self._results = []

        from .scanner_tab import AutoScreenWorker
        self._worker = AutoScreenWorker(config, top_n=10)
        self._worker.progress.connect(self._on_progress)
        self._worker.result_ready.connect(self._on_single_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(int, str)
    def _on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self.lbl_result_info.setText(msg)
        self.statusBar().showMessage(msg)

    @pyqtSlot(dict)
    def _on_single_result(self, result: dict):
        self._results.append(result)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        self._set_row(row, result, rank=0)

    @pyqtSlot(list)
    def _on_finished(self, results: list):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🚀  立即选股")

        if not results:
            self.lbl_result_info.setText("⚠ 未发现符合尾盘条件的股票（建议在14:30后运行）")
            self.statusBar().showMessage("选股完成，暂无符合条件股票")
            return

        # 按买入价值重排
        from .scanner_tab import _buy_value_score
        sorted_r = sorted(results, key=_buy_value_score, reverse=True)
        self._results = sorted_r
        self._fill_table(sorted_r)

        strong_cnt = sum(1 for r in sorted_r if r.get('recommendation') == 'strong_buy')
        buy_cnt    = sum(1 for r in sorted_r if r.get('recommendation') in ('strong_buy', 'buy'))
        self.lbl_result_info.setText(
            f"共 {len(sorted_r)} 只  |  强烈买入 🔥 {strong_cnt} 只  |  建议买入 ✅ {buy_cnt} 只")

        now = datetime.now().strftime('%H:%M')
        self._card_total.set_value(str(len(sorted_r)))
        self._card_strong.set_value(str(strong_cnt))
        self._card_buy.set_value(str(buy_cnt - strong_cnt))
        self._card_time.set_value(now)

        # 保存并刷新信号
        try:
            self.db.save_scan_results(sorted_r)
            self.db.clear_today_signals()
            from .scanner_tab import _save_as_signals
            saved = _save_as_signals(self.db, sorted_r)
            tip = f"  ✓ {saved} 条信号写入看板" if saved else ""
            self.statusBar().showMessage(f"选股完成，精选 {len(sorted_r)} 只{tip}")
        except Exception as e:
            logger.warning(f"保存信号失败: {e}")

        self._load_today_signals()

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🚀  立即选股")
        self.lbl_result_info.setText(f"⚠ 错误：{msg[:80]}")
        QMessageBox.warning(self, "选股出错", msg)

    # =========================================================
    # 详情面板
    # =========================================================

    @pyqtSlot(int, int, int, int)
    def _on_row_changed(self, cur_row, _1, _2, _3):
        if cur_row < 0 or cur_row >= len(self._results):
            return
        self._show_detail(self._results[cur_row])

    def _on_row_changed_by_click(self, index):
        row = index.row()
        if 0 <= row < len(self._results):
            self._show_detail(self._results[row])

    def _show_signal_detail(self, r: dict):
        """侧边栏点击信号行 → 高亮表格 + 显示详情"""
        sym = r.get('symbol', '')
        for i, res in enumerate(self._results):
            if res.get('symbol') == sym:
                self.tbl.selectRow(i)
                self._show_detail(res)
                return
        self._show_detail(r)

    def _show_detail(self, r: dict):
        name   = r.get('name', '')
        sym    = r.get('symbol', '')
        price  = float(r.get('price') or 0)
        change = float(r.get('change_pct') or 0)
        total  = float(r.get('total_score') or 0)
        t_sc   = float(r.get('technical_score') or total)
        f_sc   = float(r.get('fundamental_score') or 0)
        rec    = r.get('recommendation', 'hold')
        macd   = r.get('macd_signal', 'neutral')
        rsi    = r.get('rsi')
        vr     = r.get('volume_ratio')
        tr     = r.get('turnover_rate')
        pe     = r.get('pe_ratio')
        pb     = r.get('pb_ratio')
        ma5    = r.get('ma5')
        ma10   = r.get('ma10')
        ma20   = r.get('ma20')
        ma60   = r.get('ma60')
        target = r.get('target_price')
        stop   = r.get('stop_loss')
        cap    = r.get('market_cap')
        patterns = r.get('pattern_names') or []
        reason = r.get('reason', '')

        # 标题
        self.det_title.setText(f"  {name}  ({sym})")
        self.det_title.setStyleSheet(
            "font-size:15px;font-weight:bold;color:#e6edf3;background:transparent;")

        c_color = COLOR_UP if change >= 0 else COLOR_DOWN
        sign = '+' if change >= 0 else ''
        self.det_price.setText(f"¥ {price:.2f}")
        self.det_price.setStyleSheet(
            f"font-size:20px;font-weight:bold;color:{c_color};background:transparent;")
        self.det_change.setText(f"{sign}{change:.2f}%")
        self.det_change.setStyleSheet(
            f"font-size:14px;font-weight:bold;color:{c_color};background:transparent;")

        rec_color = REC_COLORS.get(rec, COLOR_FLAT)
        self.det_rec.setText(f"  {REC_TEXTS.get(rec, rec)}  ")
        self.det_rec.setStyleSheet(
            f"font-size:13px;font-weight:bold;color:{rec_color};"
            f"border:1px solid {rec_color};border-radius:4px;"
            "background:transparent;padding:2px 10px;")

        def fv(v, d=2, suffix=''):
            try:
                return f"{float(v):.{d}f}{suffix}" if v is not None else '--'
            except Exception:
                return '--'

        # 左列：核心数据
        cap_str = (f"{float(cap)/1e8:.0f}亿" if cap else '--')
        self.det_left.setText(
            f"综合评分   <b style='color:{score_color(total)};'>{total:.0f}</b> / 100\n"
            f"技术评分   <b style='color:{score_color(t_sc)};'>{t_sc:.0f}</b> / 100\n"
            f"基本面分   {f_sc:.0f} / 100\n"
            f"市值       {cap_str}\n"
            f"PE 市盈率  {fv(pe, 1)}\n"
            f"PB 市净率  {fv(pb, 2)}\n"
            f"目标价     <b style='color:{COLOR_UP};'>¥ {fv(target)}</b>\n"
            f"止损价     <b style='color:{COLOR_DOWN};'>¥ {fv(stop)}</b>"
        )
        self.det_left.setTextFormat(Qt.RichText)

        # 右列：技术指标
        macd_txt   = MACD_TEXTS.get(macd, macd)
        macd_color = (COLOR_UP if macd == 'golden_cross'
                      else COLOR_DOWN if macd == 'dead_cross'
                      else COLOR_YELLOW if macd == 'bullish' else COLOR_FLAT)
        self.det_right.setText(
            f"MA5 / MA10   {fv(ma5)} / {fv(ma10)}\n"
            f"MA20 / MA60  {fv(ma20)} / {fv(ma60)}\n"
            f"MACD 信号    <b style='color:{macd_color};'>{macd_txt}</b>\n"
            f"RSI (14)     {fv(rsi, 1)}\n"
            f"量比         {fv(vr, 1)}X\n"
            f"换手率       {fv(tr, 1)}%\n"
            f"\n"
            f"买入：14:40–14:55\n"
            f"卖出：次日 9:30–10:30"
        )
        self.det_right.setTextFormat(Qt.RichText)

        # 中间：形态 + 原因
        pnames = patterns if isinstance(patterns, list) else []
        p_str  = '  ·  '.join(pnames) if pnames else (reason or '—')
        self.det_center.setText(
            f"触发形态\n"
            f"{'  ·  '.join(pnames) if pnames else '—'}\n\n"
            f"操作依据\n"
            f"{reason or '—'}\n\n"
            f"止盈目标  +{((float(target)/price-1)*100 if target and price else 0):.1f}%\n"
            f"止损幅度  -{((price-float(stop))/price*100 if stop and price else 0):.1f}%"
        )

    # =========================================================
    # 定时器 / 辅助
    # =========================================================

    def _setup_timers(self):
        t = QTimer(self)
        t.timeout.connect(self._refresh_clock)
        t.start(1000)

        QTimer.singleShot(2000, self._refresh_indices)
        t2 = QTimer(self)
        t2.timeout.connect(self._refresh_indices)
        t2.start(120_000)

        t3 = QTimer(self)
        t3.timeout.connect(self._refresh_timing_hint)
        t3.start(60_000)

    def _refresh_clock(self):
        now  = datetime.now()
        wd, h, m = now.weekday(), now.hour, now.minute
        t = h * 60 + m
        self.lbl_time.setText(now.strftime("  %Y-%m-%d  %H:%M:%S"))
        if wd < 5:
            if (570 <= t <= 691) or (780 <= t <= 900):
                self.lbl_status.setText("🟢 交易中")
                self.lbl_status.setStyleSheet(f"font-size:12px;color:{COLOR_UP};background:transparent;")
            elif t < 570:
                self.lbl_status.setText("⏰ 等待开盘")
                self.lbl_status.setStyleSheet("font-size:12px;color:#e3b341;background:transparent;")
            else:
                self.lbl_status.setText("🔴 已收盘")
                self.lbl_status.setStyleSheet("font-size:12px;color:#8b949e;background:transparent;")
        else:
            self.lbl_status.setText("⛔ 休市")
            self.lbl_status.setStyleSheet("font-size:12px;color:#484f58;background:transparent;")

    def _refresh_timing_hint(self):
        now = datetime.now()
        h, m = now.hour, now.minute
        t = h * 60 + m
        wd = now.weekday()
        if wd >= 5:
            msg = "今日休市  周一重新开始"
        elif t < 570:
            msg = f"距开盘还有 {570-t} 分钟\n9:30 盘前可先准备"
        elif 570 <= t < 840:
            msg = "📊 交易时段\n建议 14:30 后运行选股"
        elif 840 <= t <= 900:
            msg = "🔥 尾盘黄金时段\n14:40–14:55 最佳买入"
        else:
            msg = "收盘后模式\n可回顾今日信号"
        self.lbl_timing.setText(msg)

    def _refresh_indices(self):
        try:
            from src.data.data_fetcher import DataFetcher
            indices = DataFetcher().get_index_data()
            pairs = [
                ('000001', self.lbl_sh,  '上证'),
                ('399001', self.lbl_sz,  '深证'),
                ('399006', self.lbl_cyb, '创业板'),
            ]
            for code, lbl, prefix in pairs:
                if code in indices:
                    info  = indices[code]
                    pct   = float(info.get('change_pct', 0) or 0)
                    price = float(info.get('price', 0) or 0)
                    sign  = '+' if pct >= 0 else ''
                    color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else COLOR_FLAT)
                    lbl.setText(f"{prefix} {price:.2f}  {sign}{pct:.2f}%")
                    lbl.setStyleSheet(
                        f"font-size:12px;color:{color};background:transparent;min-width:140px;")
        except Exception as e:
            logger.debug(f"刷新指数失败: {e}")

    # =========================================================
    # 菜单
    # =========================================================

    def _setup_menu(self):
        bar = self.menuBar()
        bar.setStyleSheet(
            "QMenuBar{background:#0d1117;color:#c9d1d9;border-bottom:1px solid #21262d;}"
            "QMenuBar::item:selected{background:#21262d;}"
            "QMenu{background:#161b22;color:#e6edf3;border:1px solid #30363d;}"
            "QMenu::item:selected{background:#21262d;}")

        file_m = bar.addMenu("文件(&F)")
        act_q = QAction("退出(&Q)", self)
        act_q.setShortcut("Ctrl+Q")
        act_q.triggered.connect(QApplication.quit)
        file_m.addAction(act_q)

        help_m = bar.addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._show_about)
        help_m.addAction(act_about)

    def _open_settings(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        from .settings_tab import SettingsTab
        dlg = QDialog(self)
        dlg.setWindowTitle("策略参数设置")
        dlg.resize(700, 560)
        dlg.setStyleSheet(DARK_STYLE)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(SettingsTab(self.db))
        dlg.exec_()

    def _show_about(self):
        QMessageBox.about(self, "关于 SmartSelect",
            "<h3>SmartSelect  ·  尾盘选股策略</h3>"
            "<p><b>策略逻辑：</b>下午14:30后选股，次日9:30冲高卖出</p>"
            "<ul>"
            "<li>涨幅 +2% ~ +7%（有上攻动力但不追高）</li>"
            "<li>量比 ≥ 1.5（放量，资金主动介入）</li>"
            "<li>换手率 3% ~ 15%（活跃，筹码不散乱）</li>"
            "<li>价格在 MA60 之上（趋势向上）</li>"
            "<li>至少 2 项技术形态达标</li>"
            "</ul>"
            "<b>数据来源：</b>AKShare（开源免费）<br><br>"
            "<span style='color:#f85149;'>⚠ 仅供个人学习，不构成投资建议</span>")

    def closeEvent(self, event):
        self.db.close()
        event.accept()


# =========================================================
# 辅助组件
# =========================================================

class _SideCard(QFrame):
    """左侧统计卡片（小号）"""
    def __init__(self, title: str, value: str, color: str):
        super().__init__()
        self.setStyleSheet("QFrame{background:transparent;border:none;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self._lbl_t = QLabel(title)
        self._lbl_t.setStyleSheet("font-size:11px;color:#8b949e;background:transparent;")
        self._lbl_v = QLabel(value)
        self._lbl_v.setStyleSheet(
            f"font-size:16px;font-weight:bold;color:{color};background:transparent;")
        lay.addWidget(self._lbl_t)
        lay.addStretch()
        lay.addWidget(self._lbl_v)

    def set_value(self, v: str):
        self._lbl_v.setText(v)


class _SigRow(QFrame):
    """侧边栏信号条目"""
    clicked = pyqtSignal()

    def __init__(self, s: dict, is_strong: bool):
        super().__init__()
        is_strong = s.get('recommendation') == 'strong_buy'
        bg  = '#0f1f0f' if is_strong else '#161b22'
        bd  = '#1a7f37' if is_strong else '#21262d'
        self.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {bd};"
            "border-radius:5px;cursor:pointer;}}"
            "QFrame:hover{border-color:#58a6ff;}")
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        pfx = "🔥" if is_strong else "✅"
        lbl_name = QLabel(f"{pfx} {s.get('name','')} {s.get('symbol','')}")
        lbl_name.setStyleSheet("font-size:11px;color:#c9d1d9;background:transparent;")

        price = float(s.get('price') or 0)
        chg   = float(s.get('change_pct') or 0)
        sign  = '+' if chg >= 0 else ''
        clr   = COLOR_UP if chg >= 0 else COLOR_DOWN
        lbl_p = QLabel(f"{price:.2f} {sign}{chg:.1f}%")
        lbl_p.setStyleSheet(f"font-size:11px;color:{clr};background:transparent;")

        lay.addWidget(lbl_name, 1)
        lay.addWidget(lbl_p)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


def _idx_lbl() -> QLabel:
    lbl = QLabel("-- : --  --")
    lbl.setStyleSheet("font-size:12px;color:#484f58;background:transparent;min-width:140px;")
    return lbl


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#21262d;background:transparent;max-width:1px;")
    f.setFixedHeight(26)
    return f


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("background:#21262d;max-width:1px;")
    return f
