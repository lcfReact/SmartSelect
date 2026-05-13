#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智选策略 SmartSelect - 个人自用量化选股工具
启动入口

使用方式：
    python main.py

首次运行请先安装依赖：
    pip install -r requirements.txt
"""
import sys
import os
import logging
import traceback

# 将项目根目录加入搜索路径
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('smartselect')


def _install_exception_hook():
    """安装全局异常捕获，防止未处理异常静默崩溃"""
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(f"未捕获异常:\n{msg}")
        # 尝试显示错误对话框
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None, "程序异常",
                    f"发生未预期的错误，请记录以下信息并重启：\n\n"
                    f"{exc_type.__name__}: {exc_value}\n\n"
                    f"详细信息已写入控制台"
                )
        except Exception:
            pass
    sys.excepthook = _hook

    # 也捕获 PyQt5 线程内部异常
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
        def _qt_handler(msg_type, context, message):
            if msg_type in (QtMsgType.QtWarningMsg,):
                logger.debug(f"Qt Warning: {message}")
            elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                logger.error(f"Qt Critical: {message}")
            else:
                pass
        qInstallMessageHandler(_qt_handler)
    except Exception:
        pass


def main():
    _install_exception_hook()
    try:
        from PyQt5.QtCore import Qt, QCoreApplication
        from PyQt5.QtWidgets import QApplication, QSplashScreen, QLabel
        from PyQt5.QtGui import QPixmap, QColor, QFont

        # 高 DPI 适配
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)
        app.setApplicationName("SmartSelect")
        app.setApplicationDisplayName("智选策略 SmartSelect")
        app.setOrganizationName("Personal")

        # ===== 启动画面 =====
        splash_pix = QPixmap(480, 280)
        splash_pix.fill(QColor('#0d1117'))
        splash = QSplashScreen(splash_pix)
        splash.setStyleSheet("font-family: 'Microsoft YaHei UI';")

        def _show_msg(msg):
            splash.showMessage(
                f"  {msg}",
                Qt.AlignBottom | Qt.AlignLeft,
                QColor('#8b949e')
            )
            app.processEvents()

        splash.show()
        _show_msg("正在初始化…")

        # 初始化数据库
        _show_msg("正在初始化数据库…")
        from src.database.db_manager import DatabaseManager
        db = DatabaseManager()
        db.initialize()
        logger.info("数据库初始化完成")

        # ===== 创建主窗口 =====
        _show_msg("正在加载界面…")
        from src.ui.main_window import MainWindow
        window = MainWindow(db)

        splash.finish(window)
        window.show()
        logger.info("SmartSelect 启动成功 - 尾盘选股策略")

        sys.exit(app.exec_())

    except ImportError as e:
        print(f"\n错误：缺少依赖包 - {e}")
        print("\n请先安装依赖：")
        print("    pip install -r requirements.txt\n")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
