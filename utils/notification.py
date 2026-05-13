"""
桌面通知工具 - Windows 系统托盘气泡提示
优先使用 win10toast，退回到 plyer，最后仅记录日志
"""
import logging
import threading

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str, duration: int = 5,
                      icon_path: str = None):
    """异步发送桌面通知，不阻塞主线程"""
    t = threading.Thread(
        target=_send, args=(title, message, duration, icon_path),
        daemon=True
    )
    t.start()


def _send(title: str, message: str, duration: int, icon_path: str):
    sent = False

    # 尝试 win10toast
    if not sent:
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message,
                               icon_path=icon_path,
                               duration=duration,
                               threaded=False)
            sent = True
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"win10toast 发送失败: {e}")

    # 尝试 plyer
    if not sent:
        try:
            from plyer import notification as plyer_notify
            plyer_notify.notify(
                title=title,
                message=message,
                timeout=duration
            )
            sent = True
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"plyer 发送失败: {e}")

    if not sent:
        logger.info(f"[通知] {title}: {message}")


def notify_signal(name: str, symbol: str, signal_type: str,
                  price: float, target: float, stop: float):
    """发送买入/卖出信号通知"""
    if signal_type == 'buy':
        title = f"📈 买入信号：{name}({symbol})"
        msg = (f"当前价：{price:.2f}  "
               f"目标价：{target:.2f}  "
               f"止损价：{stop:.2f}")
    else:
        title = f"📉 卖出信号：{name}({symbol})"
        msg = f"当前价：{price:.2f}，建议及时操作"
    send_notification(title, msg)


def notify_stop_loss(name: str, symbol: str, price: float, stop: float):
    """发送止损预警通知"""
    title = f"⚠ 止损预警：{name}({symbol})"
    msg = f"当前价 {price:.2f} 触及止损价 {stop:.2f}，请立即处理！"
    send_notification(title, msg, duration=10)


def notify_take_profit(name: str, symbol: str, price: float, profit_pct: float):
    """发送止盈提示通知"""
    title = f"✅ 止盈提示：{name}({symbol})"
    msg = f"已达目标价！当前价 {price:.2f}，浮盈 +{profit_pct:.1f}%"
    send_notification(title, msg)
