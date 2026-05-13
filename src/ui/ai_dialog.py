"""
AI 分析结果展示对话框
支持流式输出（打字机效果），可分析单只股票/持仓组合/今日信号汇总
"""
import logging

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)


# ===== 后台 AI 请求线程 =====

class AIWorker(QThread):
    chunk_received = pyqtSignal(str)   # 流式块
    finished = pyqtSignal(str)         # 完整结果
    error = pyqtSignal(str)

    def __init__(self, analyst, prompt: str):
        super().__init__()
        self.analyst = analyst
        self.prompt = prompt
        self._running = True

    def run(self):
        try:
            result = self.analyst.chat(
                self.prompt,
                stream=True,
                on_chunk=lambda c: self.chunk_received.emit(c) if self._running else None
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._running = False


# ===== AI 分析对话框 =====

class AIAnalysisDialog(QDialog):
    """
    通用 AI 分析对话框，流式显示 AI 输出
    Usage:
        dlg = AIAnalysisDialog(parent, title="贵州茅台 AI 分析", analyst=ai, prompt="...")
        dlg.exec_()
    """
    def __init__(self, parent, title: str, analyst, prompt: str):
        super().__init__(parent)
        self.analyst = analyst
        self.prompt = prompt
        self._worker = None
        self._full_text = ""

        self.setWindowTitle(f"AI 智能分析 — {title}")
        self.setMinimumSize(720, 520)
        self.resize(800, 580)
        self._setup_ui()
        self._start()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()
        lbl = QLabel("🤖  AI 分析结果")
        lbl.setStyleSheet("font-size:14px;font-weight:bold;color:#58a6ff;")
        self.lbl_status = QLabel("正在分析…")
        self.lbl_status.setStyleSheet("color:#8b949e;font-size:12px;")
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(self.lbl_status)
        lay.addLayout(header)

        # 主文本区
        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d1117;
                color: #e6edf3;
                border: 1px solid #21262d;
                border-radius: 6px;
                font-size: 14px;
                line-height: 180%;
                padding: 10px;
            }
        """)
        font = QFont("Microsoft YaHei UI", 13)
        self.text_area.setFont(font)
        lay.addWidget(self.text_area)

        # 免责声明
        disc = QLabel("⚠ 以上内容由 AI 自动生成，仅供参考，不构成投资建议，股市有风险，投资需谨慎。")
        disc.setStyleSheet("color:#484f58;font-size:11px;")
        disc.setWordWrap(True)
        lay.addWidget(disc)

        # 按钮行
        btn_row = QHBoxLayout()
        self.btn_copy = QPushButton("📋 复制")
        self.btn_copy.setFixedWidth(80)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_retry = QPushButton("🔄 重新分析")
        self.btn_retry.setFixedWidth(110)
        self.btn_retry.clicked.connect(self._start)
        btn_close = QPushButton("关闭")
        btn_close.setFixedWidth(70)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_copy)
        btn_row.addWidget(self.btn_retry)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

    def _start(self):
        self.text_area.setPlainText("")
        self._full_text = ""
        self.lbl_status.setText("🤖 AI 分析中…")
        self.btn_retry.setEnabled(False)

        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)

        self._worker = AIWorker(self.analyst, self.prompt)
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_chunk(self, chunk: str):
        cursor = self.text_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(chunk)
        self.text_area.setTextCursor(cursor)
        self.text_area.ensureCursorVisible()

    def _on_done(self, text: str):
        self._full_text = text
        self.lbl_status.setText("✅ 分析完成")
        self.btn_retry.setEnabled(True)

    def _on_error(self, msg: str):
        self.text_area.setPlainText(f"❌ AI 分析失败：\n{msg}\n\n请检查设置页中的 API 配置。")
        self.lbl_status.setText("❌ 出错")
        self.btn_retry.setEnabled(True)

    def _copy(self):
        from PyQt5.QtWidgets import QApplication
        text = self.text_area.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.btn_copy.setText("已复制")
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy.setText("📋 复制"))

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        event.accept()


# ===== 工具函数：检查 AI 是否已配置 =====

def get_analyst(db):
    """
    从配置中读取 AI 设置，返回 AIAnalyst 实例
    未配置时返回 None
    """
    try:
        from src.ai.ai_analyst import AIAnalyst
        cfg = db.get_config()
        ai_cfg = cfg.get('ai', {})
        key = ai_cfg.get('api_key', '').strip()
        url = ai_cfg.get('base_url', '').strip()
        model = ai_cfg.get('model', '').strip()
        if not all([key, url, model]):
            return None
        return AIAnalyst(key, url, model)
    except Exception:
        return None


def require_ai(db, parent) -> object:
    """
    获取 AI 客户端，如未配置则弹窗提示并返回 None
    """
    analyst = get_analyst(db)
    if analyst is None:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            parent, "AI 未配置",
            "请先在【设置】页面配置 AI API Key、Base URL 和模型名称，\n"
            "支持 DeepSeek、OpenAI、通义千问、Kimi 等。"
        )
    return analyst
