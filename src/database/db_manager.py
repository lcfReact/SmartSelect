"""
SQLite数据库管理模块
负责持仓、信号、交易记录、自选股等数据的持久化存储
"""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.data_dir = Path.home() / '.smartselect'
        self.db_path = self.data_dir / 'data.db'
        self.config_path = self.data_dir / 'config.json'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = None

    def initialize(self):
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._ensure_default_config()
        logger.info(f"数据库初始化完成: {self.db_path}")

    def _create_tables(self):
        sql_statements = [
            # 信号记录
            """CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                signal_type TEXT NOT NULL,
                price REAL,
                target_price REAL,
                stop_loss REAL,
                fundamental_score REAL,
                technical_score REAL,
                total_score REAL,
                reason TEXT,
                signal_strength INTEGER DEFAULT 3,
                recommendation TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )""",
            # 持仓管理
            """CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                buy_price REAL NOT NULL,
                quantity REAL DEFAULT 100,
                target_price REAL,
                stop_loss REAL,
                buy_date TEXT,
                notes TEXT,
                status TEXT DEFAULT 'holding',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )""",
            # 成交记录
            """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                buy_price REAL,
                sell_price REAL,
                quantity REAL DEFAULT 100,
                buy_date TEXT,
                sell_date TEXT,
                profit_loss REAL,
                profit_pct REAL,
                reason TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )""",
            # 自选股
            """CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT,
                added_date TEXT DEFAULT (datetime('now', 'localtime'))
            )""",
            # 扫描结果缓存
            """CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                price REAL,
                change_pct REAL,
                fundamental_score REAL,
                technical_score REAL,
                total_score REAL,
                ma20 REAL,
                ma60 REAL,
                macd_signal TEXT,
                rsi REAL,
                volume_ratio REAL,
                recommendation TEXT,
                scan_time TEXT DEFAULT (datetime('now', 'localtime'))
            )"""
        ]
        cursor = self.conn.cursor()
        for sql in sql_statements:
            cursor.execute(sql)
        self.conn.commit()

    def _ensure_default_config(self):
        if not self.config_path.exists():
            config = {
                "fundamental": {
                    "min_profit_growth": 15,
                    "max_debt_ratio": 60,
                    "max_pe_ratio_multiplier": 1.5,
                    "require_positive_cashflow": True
                },
                "technical": {
                    "ma_short": 20,
                    "ma_long": 60,
                    "rsi_min": 40,
                    "rsi_max": 70,
                    "volume_increase_pct": 30
                },
                "risk": {
                    "stop_loss_pct": 8,
                    "take_profit_pct": 20,
                    "max_position_pct": 10
                },
                "notifications": {
                    "enabled": True,
                    "morning_report": True,
                    "evening_report": True,
                    "signal_alert": True
                }
            }
            self.save_config(config)

    def get_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self, config):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    # ===== 信号相关 =====

    def save_signal(self, data: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals
                (symbol, name, signal_type, price, target_price, stop_loss,
                 fundamental_score, technical_score, total_score, reason,
                 signal_strength, recommendation)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get('symbol'), data.get('name'), data.get('signal_type'),
            data.get('price'), data.get('target_price'), data.get('stop_loss'),
            data.get('fundamental_score'), data.get('technical_score'),
            data.get('total_score'), data.get('reason'),
            data.get('signal_strength', 3), data.get('recommendation', 'hold')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def clear_today_signals(self):
        """清除今日的自动选股信号（每次新选股前调用，避免累积旧结果）"""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM signals
            WHERE date(created_at) = date('now', 'localtime')
        """)
        self.conn.commit()

    def get_today_signals(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM signals
            WHERE date(created_at) = date('now', 'localtime')
            ORDER BY total_score DESC
        """)
        return [dict(r) for r in cursor.fetchall()]

    def get_recent_signals(self, days: int = 7) -> list:
        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT * FROM signals
            WHERE created_at >= datetime('now', '-{days} days', 'localtime')
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]

    # ===== 持仓相关 =====

    def add_position(self, data: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO portfolio
                (symbol, name, buy_price, quantity, target_price, stop_loss, buy_date, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            data.get('symbol'), data.get('name'),
            data.get('buy_price'), data.get('quantity', 100),
            data.get('target_price'), data.get('stop_loss'),
            data.get('buy_date', datetime.now().strftime('%Y-%m-%d')),
            data.get('notes', '')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_portfolio(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM portfolio WHERE status='holding' ORDER BY created_at DESC")
        return [dict(r) for r in cursor.fetchall()]

    def update_position(self, position_id: int, data: dict):
        cursor = self.conn.cursor()
        sets = ', '.join(f"{k}=?" for k in data)
        cursor.execute(f"UPDATE portfolio SET {sets} WHERE id=?", list(data.values()) + [position_id])
        self.conn.commit()

    def close_position(self, position_id: int, sell_price: float, reason: str = ''):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM portfolio WHERE id=?", (position_id,))
        row = cursor.fetchone()
        if not row:
            return
        pos = dict(row)
        qty = pos.get('quantity', 100) or 100
        profit_loss = (sell_price - pos['buy_price']) * qty
        profit_pct = (sell_price - pos['buy_price']) / pos['buy_price'] * 100

        cursor.execute("""
            INSERT INTO transactions
                (symbol, name, buy_price, sell_price, quantity, buy_date, sell_date,
                 profit_loss, profit_pct, reason)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            pos['symbol'], pos['name'], pos['buy_price'], sell_price, qty,
            pos['buy_date'], datetime.now().strftime('%Y-%m-%d'),
            profit_loss, profit_pct, reason
        ))
        cursor.execute("UPDATE portfolio SET status='sold' WHERE id=?", (position_id,))
        self.conn.commit()

    def delete_position(self, position_id: int):
        self.conn.execute("DELETE FROM portfolio WHERE id=?", (position_id,))
        self.conn.commit()

    # ===== 交易记录相关 =====

    def get_transactions(self, limit: int = 200) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]

    def get_statistics(self) -> dict:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END) as winning_trades,
                AVG(profit_pct) as avg_return,
                SUM(profit_loss) as total_profit,
                MAX(profit_pct) as max_gain,
                MIN(profit_pct) as max_loss
            FROM transactions
        """)
        row = cursor.fetchone()
        stats = dict(row)
        total = stats.get('total_trades') or 0
        wins = stats.get('winning_trades') or 0
        stats['win_rate'] = (wins / total * 100) if total > 0 else 0.0
        return stats

    # ===== 自选股相关 =====

    def get_watchlist(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM watchlist ORDER BY added_date DESC")
        return [dict(r) for r in cursor.fetchall()]

    def add_to_watchlist(self, symbol: str, name: str = '') -> bool:
        try:
            self.conn.execute("INSERT INTO watchlist (symbol, name) VALUES (?,?)", (symbol, name))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_from_watchlist(self, symbol: str):
        self.conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
        self.conn.commit()

    # ===== 扫描结果相关 =====

    def save_scan_results(self, results: list):
        cursor = self.conn.cursor()
        for r in results:
            cursor.execute("""
                INSERT INTO scan_results
                    (symbol, name, price, change_pct, fundamental_score, technical_score,
                     total_score, ma20, ma60, macd_signal, rsi, volume_ratio, recommendation)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r.get('symbol'), r.get('name'), r.get('price'), r.get('change_pct'),
                r.get('fundamental_score'), r.get('technical_score'), r.get('total_score'),
                r.get('ma20'), r.get('ma60'), r.get('macd_signal'),
                r.get('rsi'), r.get('volume_ratio'), r.get('recommendation')
            ))
        self.conn.commit()

    def get_latest_scan_results(self, limit: int = 100) -> list:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM scan_results
            WHERE scan_time >= datetime('now', '-1 day', 'localtime')
            ORDER BY total_score DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]

    def close(self):
        if self.conn:
            self.conn.close()
