"""
SmartSelect Web 服务 - FastAPI 后端
提供 REST API + WebSocket 实时进度推送
"""
import asyncio
import json
import logging
import math
import os
import sys
import threading
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 把项目根目录加入 Python 搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('smartselect.web')

# ── 初始化数据库 ──────────────────────────────────────────────────────
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()

app = FastAPI(title="SmartSelect API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── 全局扫描状态 ──────────────────────────────────────────────────────
_scan_lock = threading.Lock()
_scan_state = {
    "running": False,
    "progress": 0,
    "message":  "就绪",
    "results":  [],
    "last_scan": None,
}
_ws_clients: list[WebSocket] = []


# =========================================================
# WebSocket — 实时推送扫描进度
# =========================================================

@app.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        # 连接后立即推送当前状态
        await ws.send_json(_safe_state())
        while True:
            await asyncio.sleep(1)   # 保持心跳
    except WebSocketDisconnect:
        _ws_clients.remove(ws)
    except Exception:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


async def _broadcast(data: dict):
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


def _push(progress: int, message: str, results: list = None):
    """在工作线程中安全地广播状态"""
    _scan_state["progress"] = progress
    _scan_state["message"]  = message
    if results is not None:
        _scan_state["results"] = results
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _broadcast(_safe_state()), loop
            )
    except Exception:
        pass


# =========================================================
# API 路由
# =========================================================

@app.get("/")
async def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/api/status")
async def api_status():
    return _safe_state()


@app.get("/api/signals")
async def api_signals():
    """今日信号"""
    try:
        signals = db.get_today_signals()
        return {"ok": True, "data": _clean_list(signals)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/market")
async def api_market():
    """三大指数行情"""
    try:
        from src.data.data_fetcher import DataFetcher
        indices = DataFetcher().get_index_data()
        out = {}
        for code, label in [('000001','上证'), ('399001','深证'), ('399006','创业板')]:
            if code in indices:
                info = indices[code]
                out[code] = {
                    "label":      label,
                    "price":      _safe_num(info.get('price')),
                    "change_pct": _safe_num(info.get('change_pct')),
                }
        return {"ok": True, "data": out}
    except Exception as e:
        logger.warning(f"行情获取失败: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/api/scan")
async def api_scan(background_tasks: BackgroundTasks):
    """触发全市场自动选股（异步后台）"""
    if _scan_state["running"]:
        return {"ok": False, "error": "扫描正在进行中"}
    background_tasks.add_task(_run_scan)
    return {"ok": True, "message": "选股任务已启动"}


@app.post("/api/scan/stop")
async def api_scan_stop():
    _scan_state["running"] = False
    return {"ok": True}


# =========================================================
# 后台选股任务（复用现有策略模块）
# =========================================================

def _run_scan():
    with _scan_lock:
        if _scan_state["running"]:
            return
        _scan_state["running"] = True
        _scan_state["results"] = []

    try:
        _push(2, "正在连接数据源…")
        config = db.get_config()

        import pandas as pd
        import time
        from src.data.data_fetcher import DataFetcher
        from src.strategy.signal_engine import SignalEngine
        from src.strategy.auto_screener import (
            pre_filter, select_candidates, final_select, DEFAULT_PRE_FILTER
        )

        fetcher = DataFetcher()
        engine  = SignalEngine(config)
        all_df  = pd.DataFrame()

        for attempt in range(3):
            if not _scan_state["running"]:
                return
            _push(3 + attempt * 4, f"行情获取中（{attempt+1}/3）…")
            try:
                all_df = fetcher.get_realtime_quotes()
                if not all_df.empty:
                    break
            except Exception as e:
                logger.warning(f"行情第 {attempt+1} 次失败: {e}")
            if attempt < 2:
                time.sleep(3)

        if all_df.empty:
            _push(0, "获取行情失败，请检查网络后重试")
            return

        _push(18, f"已获取 {len(all_df)} 只 A 股，正在尾盘预筛…")

        cfg_pre   = {**DEFAULT_PRE_FILTER, **config.get('pre_filter', {})}
        filtered  = pre_filter(all_df, cfg_pre)
        if filtered.empty:
            _push(0, "预筛无结果（建议在14:30后运行）")
            return

        candidates = select_candidates(filtered, 80)
        total = len(candidates)
        _push(22, f"预筛通过 {total} 只，开始深度技术分析…")

        results = []
        for idx, (_, row) in enumerate(candidates.iterrows()):
            if not _scan_state["running"]:
                break
            symbol = str(row.get('symbol', '')).strip()
            name   = str(row.get('name', symbol)).strip()
            if not symbol:
                continue
            pct = int(22 + (idx + 1) / total * 73)
            _push(pct, f"[{idx+1}/{total}] 分析 {name}({symbol})…")
            try:
                quote   = {k: v for k, v in row.to_dict().items()
                           if v is not None and str(v) not in ('nan', 'None', '')}
                hist_df = fetcher.get_historical_data(symbol, days=120)
                result  = engine.analyze(symbol, name, quote, hist_df)
                if result:
                    result.pop('_tech', None)
                    result = _sanitize(result)
                    results.append(result)
                    _push(pct, _scan_state["message"], list(results))
            except Exception as e:
                logger.debug(f"分析 {symbol} 跳过: {e}")

        # 精选 + 排序
        try:
            final = final_select(results)
        except Exception as e:
            logger.warning(f"final_select 异常: {e}")
            final = sorted(results, key=_bv_score, reverse=True)[:10]

        # 保存信号
        try:
            db.save_scan_results(final)
            db.clear_today_signals()
            _save_signals(final)
        except Exception as e:
            logger.warning(f"保存信号失败: {e}")

        _scan_state["last_scan"] = datetime.now().strftime('%H:%M:%S')
        _push(100, f"选股完成，精选 {len(final)} 只", final)

    except Exception as e:
        logger.exception(f"选股异常: {e}")
        _push(0, f"选股出错：{e}")
    finally:
        _scan_state["running"] = False


# =========================================================
# 工具函数
# =========================================================

def _safe_state() -> dict:
    return {
        "running":   _scan_state["running"],
        "progress":  _scan_state["progress"],
        "message":   _scan_state["message"],
        "results":   _clean_list(_scan_state["results"]),
        "last_scan": _scan_state["last_scan"],
    }


def _clean_list(data: list) -> list:
    return [_sanitize(r) for r in data]


def _sanitize(r: dict) -> dict:
    out = {}
    for k, v in r.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
        elif isinstance(v, (list, dict)):
            out[k] = v
        else:
            out[k] = v
    return out


def _safe_num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    except Exception:
        return None


def _bv_score(r: dict) -> float:
    total = float(r.get('total_score') or 0)
    t_sc  = float(r.get('technical_score') or 0)
    rec   = r.get('recommendation', 'hold')
    macd  = r.get('macd_signal', 'neutral')
    bonus = {'strong_buy': 18, 'buy': 10}.get(rec, 0)
    macd_b = {'golden_cross': 12, 'bullish': 5, 'dead_cross': -12}.get(macd, 0)
    return total * 0.55 + t_sc * 0.25 + bonus + macd_b


def _save_signals(results: list):
    config = db.get_config()
    risk   = config.get('risk', {})
    sl     = risk.get('stop_loss_pct',   4.0) / 100
    tp     = risk.get('take_profit_pct', 4.0) / 100
    for r in results:
        if r.get('recommendation') not in ('strong_buy', 'buy'):
            continue
        price = float(r.get('price') or 0)
        total = float(r.get('total_score') or 50)
        patterns = r.get('pattern_names') or []
        reason   = '、'.join(patterns) if isinstance(patterns, list) else str(patterns)
        db.save_signal({
            **r,
            'signal_type':    'buy',
            'target_price':   round(price * (1 + tp), 2),
            'stop_loss':      round(price * (1 - sl), 2),
            'signal_strength': max(1, min(5, int(total / 20))),
            'reason':          reason or r.get('reason', '尾盘强势'),
        })


# =========================================================
# 入口
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"SmartSelect Web 启动，端口 {port}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
