"""
设置标签页 - 策略参数配置
"""
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget, QCheckBox,
)

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.NoFrame)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(20, 16, 20, 20)
        content_lay.setSpacing(16)

        # 标题
        lbl = QLabel("策略参数配置")
        lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#f0883e;")
        content_lay.addWidget(lbl)

        # === 基本面参数 ===
        gp_fund = QGroupBox("基本面参数")
        form_fund = QFormLayout(gp_fund)
        form_fund.setSpacing(10)
        form_fund.setLabelAlignment(Qt.AlignRight)

        self.spin_pe_max = QDoubleSpinBox()
        self.spin_pe_max.setRange(10, 200)
        self.spin_pe_max.setSuffix("  倍（市盈率上限，超过此值降分）")
        self.spin_pe_max.setDecimals(0)

        self.spin_pb_max = QDoubleSpinBox()
        self.spin_pb_max.setRange(0.5, 30)
        self.spin_pb_max.setSuffix("  倍（市净率上限）")
        self.spin_pb_max.setDecimals(1)

        self.spin_min_cap = QDoubleSpinBox()
        self.spin_min_cap.setRange(0, 10000)
        self.spin_min_cap.setSuffix("  亿元（最小市值门槛）")
        self.spin_min_cap.setDecimals(0)

        form_fund.addRow("PE 上限：", self.spin_pe_max)
        form_fund.addRow("PB 上限：", self.spin_pb_max)
        form_fund.addRow("最小市值：", self.spin_min_cap)
        content_lay.addWidget(gp_fund)

        # === 技术面参数 ===
        gp_tech = QGroupBox("技术面参数")
        form_tech = QFormLayout(gp_tech)
        form_tech.setSpacing(10)
        form_tech.setLabelAlignment(Qt.AlignRight)

        self.spin_ma_short = QSpinBox()
        self.spin_ma_short.setRange(5, 30)
        self.spin_ma_short.setSuffix("  日（短期均线）")

        self.spin_ma_long = QSpinBox()
        self.spin_ma_long.setRange(20, 250)
        self.spin_ma_long.setSuffix("  日（长期趋势均线）")

        self.spin_rsi_min = QSpinBox()
        self.spin_rsi_min.setRange(20, 60)
        self.spin_rsi_min.setSuffix("  （RSI 下限，低于此值超卖）")

        self.spin_rsi_max = QSpinBox()
        self.spin_rsi_max.setRange(60, 90)
        self.spin_rsi_max.setSuffix("  （RSI 上限，高于此值超买）")

        self.spin_vol_inc = QSpinBox()
        self.spin_vol_inc.setRange(10, 200)
        self.spin_vol_inc.setSuffix("  %（量比放大门槛）")

        form_tech.addRow("短期均线：", self.spin_ma_short)
        form_tech.addRow("长期均线：", self.spin_ma_long)
        form_tech.addRow("RSI 下限：", self.spin_rsi_min)
        form_tech.addRow("RSI 上限：", self.spin_rsi_max)
        form_tech.addRow("放量门槛：", self.spin_vol_inc)
        content_lay.addWidget(gp_tech)

        # === 风控参数 ===
        gp_risk = QGroupBox("风险控制参数")
        form_risk = QFormLayout(gp_risk)
        form_risk.setSpacing(10)
        form_risk.setLabelAlignment(Qt.AlignRight)

        self.spin_stop_loss = QDoubleSpinBox()
        self.spin_stop_loss.setRange(1, 20)
        self.spin_stop_loss.setDecimals(1)
        self.spin_stop_loss.setSuffix("  %（次日止损比例）")

        self.spin_take_profit = QDoubleSpinBox()
        self.spin_take_profit.setRange(1, 50)
        self.spin_take_profit.setDecimals(1)
        self.spin_take_profit.setSuffix("  %（次日冲高目标）")

        self.spin_max_position = QDoubleSpinBox()
        self.spin_max_position.setRange(1, 100)
        self.spin_max_position.setDecimals(0)
        self.spin_max_position.setSuffix("  %（单只最大仓位）")

        form_risk.addRow("次日止损：", self.spin_stop_loss)
        form_risk.addRow("冲高目标：", self.spin_take_profit)
        form_risk.addRow("单只上限：", self.spin_max_position)

        lbl_risk_hint = QLabel(
            "📌 尾盘策略建议：止损3-5%，冲高目标3-5%，次日9:30-10:30卖出。\n"
            "单只仓位建议10-20%，总仓位不超过50%，严格执行止损纪律。")
        lbl_risk_hint.setStyleSheet("color:#e3b341;font-size:12px;")
        lbl_risk_hint.setWordWrap(True)
        form_risk.addRow("", lbl_risk_hint)
        content_lay.addWidget(gp_risk)

        # === 通知设置 ===
        gp_notify = QGroupBox("通知提醒设置")
        form_notify = QFormLayout(gp_notify)
        form_notify.setSpacing(10)

        self.chk_notify = QCheckBox("启用桌面通知")
        self.chk_morning = QCheckBox("早盘策略摘要（9:00）")
        self.chk_evening = QCheckBox("收盘总结报告（15:30）")
        self.chk_signal = QCheckBox("实时信号提醒")

        form_notify.addRow("", self.chk_notify)
        form_notify.addRow("", self.chk_morning)
        form_notify.addRow("", self.chk_evening)
        form_notify.addRow("", self.chk_signal)
        content_lay.addWidget(gp_notify)

        # === 保存按钮 ===
        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存配置")
        btn_save.setObjectName("btnBuy")
        btn_save.setFixedWidth(120)
        btn_save.clicked.connect(self._save_config)

        btn_reset = QPushButton("恢复默认")
        btn_reset.setFixedWidth(100)
        btn_reset.clicked.connect(self._reset_defaults)

        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset)
        content_lay.addLayout(btn_row)

        # 免责声明
        lbl_disc = QLabel(
            "⚠ 风险提示：本软件仅供个人学习研究，不构成任何投资建议。"
            "股市有风险，投资需谨慎。建议小额试用，逐步验证效果，严格执行止损纪律。"
        )
        lbl_disc.setStyleSheet(
            "color:#484f58;font-size:12px;"
            "background:#0d1117;border:1px solid #21262d;"
            "border-radius:6px;padding:10px;"
        )
        lbl_disc.setWordWrap(True)
        content_lay.addWidget(lbl_disc)
        content_lay.addStretch()

        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _load_config(self):
        cfg = self.db.get_config()

        fund = cfg.get('fundamental', {})
        self.spin_pe_max.setValue(float(fund.get('max_pe_ratio_multiplier', 40) or 40))
        self.spin_pb_max.setValue(float(fund.get('max_pb', 6) or 6))
        self.spin_min_cap.setValue(float(fund.get('min_market_cap', 10) or 10))

        tech = cfg.get('technical', {})
        self.spin_ma_short.setValue(int(tech.get('ma_short', 20) or 20))
        self.spin_ma_long.setValue(int(tech.get('ma_long', 60) or 60))
        self.spin_rsi_min.setValue(int(tech.get('rsi_min', 40) or 40))
        self.spin_rsi_max.setValue(int(tech.get('rsi_max', 70) or 70))
        self.spin_vol_inc.setValue(int(tech.get('volume_increase_pct', 30) or 30))

        risk = cfg.get('risk', {})
        self.spin_stop_loss.setValue(float(risk.get('stop_loss_pct', 4.0) or 4.0))
        self.spin_take_profit.setValue(float(risk.get('take_profit_pct', 4.0) or 4.0))
        self.spin_max_position.setValue(float(risk.get('max_position_pct', 15) or 15))

        notify = cfg.get('notifications', {})
        self.chk_notify.setChecked(bool(notify.get('enabled', True)))
        self.chk_morning.setChecked(bool(notify.get('morning_report', True)))
        self.chk_evening.setChecked(bool(notify.get('evening_report', True)))
        self.chk_signal.setChecked(bool(notify.get('signal_alert', True)))



    def _save_config(self):
        cfg = self.db.get_config() or {}
        cfg['fundamental'] = {
            'max_pe_ratio_multiplier': self.spin_pe_max.value(),
            'max_pb': self.spin_pb_max.value(),
            'min_market_cap': self.spin_min_cap.value(),
        }
        cfg['technical'] = {
            'ma_short': self.spin_ma_short.value(),
            'ma_long': self.spin_ma_long.value(),
            'rsi_min': self.spin_rsi_min.value(),
            'rsi_max': self.spin_rsi_max.value(),
            'volume_increase_pct': self.spin_vol_inc.value(),
        }
        cfg['risk'] = {
            'stop_loss_pct': self.spin_stop_loss.value(),
            'take_profit_pct': self.spin_take_profit.value(),
            'max_position_pct': self.spin_max_position.value(),
        }
        cfg['notifications'] = {
            'enabled': self.chk_notify.isChecked(),
            'morning_report': self.chk_morning.isChecked(),
            'evening_report': self.chk_evening.isChecked(),
            'signal_alert': self.chk_signal.isChecked(),
        }
        self.db.save_config(cfg)
        QMessageBox.information(self, "保存成功", "配置已保存")


    def _reset_defaults(self):
        reply = __import__('PyQt5.QtWidgets', fromlist=['QMessageBox']).QMessageBox.question(
            self, "恢复默认", "确认恢复所有参数为默认值？",
            __import__('PyQt5.QtWidgets', fromlist=['QMessageBox']).QMessageBox.Yes |
            __import__('PyQt5.QtWidgets', fromlist=['QMessageBox']).QMessageBox.No,
            __import__('PyQt5.QtWidgets', fromlist=['QMessageBox']).QMessageBox.No
        )
        if reply == __import__('PyQt5.QtWidgets', fromlist=['QMessageBox']).QMessageBox.Yes:
            self.spin_pe_max.setValue(40)
            self.spin_pb_max.setValue(6)
            self.spin_min_cap.setValue(10)
            self.spin_ma_short.setValue(20)
            self.spin_ma_long.setValue(60)
            self.spin_rsi_min.setValue(40)
            self.spin_rsi_max.setValue(70)
            self.spin_vol_inc.setValue(30)
            self.spin_stop_loss.setValue(4.0)
            self.spin_take_profit.setValue(4.0)
            self.spin_max_position.setValue(15)
            self.chk_notify.setChecked(True)
            self.chk_morning.setChecked(True)
            self.chk_evening.setChecked(True)
            self.chk_signal.setChecked(True)


