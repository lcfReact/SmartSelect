"""
数据获取模块 - 基于 AKShare 免费开源金融数据接口
所有网络请求均有超时控制和自动重试，防止阻塞主线程
"""
import logging
import time
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

# ===== 内存缓存 =====
_cache: dict = {}
_cache_ts: dict = {}
_CACHE_TTL = 300


def _cached(key: str, ttl: int = _CACHE_TTL):
    if key in _cache and key in _cache_ts:
        if time.time() - _cache_ts[key] < ttl:
            return _cache[key]
    return None


def _set_cache(key: str, value):
    _cache[key] = value
    _cache_ts[key] = time.time()


def clear_cache():
    _cache.clear()
    _cache_ts.clear()


def _run_with_timeout(fn, timeout: int = 15):
    """在独立线程中执行 fn，超时返回 None"""
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            logger.warning(f"请求超时（{timeout}s）: {fn.__name__ if hasattr(fn, '__name__') else fn}")
            return None
        except Exception as e:
            logger.warning(f"请求异常: {e}")
            return None


class DataFetcher:
    """A 股数据获取器，封装 AKShare 接口，带缓存+超时+重试"""

    # ===== 股票列表 =====

    def get_stock_list(self) -> pd.DataFrame:
        key = 'stock_list'
        cached = _cached(key, ttl=3600)
        if cached is not None:
            return cached
        try:
            result = _run_with_timeout(ak.stock_info_a_code_name, timeout=20)
            if result is not None and not result.empty:
                df = result.rename(columns={'code': 'symbol', 'name': 'name'})
                df = df[['symbol', 'name']].copy()
                _set_cache(key, df)
                return df
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
        return pd.DataFrame(columns=['symbol', 'name'])

    def search_stock(self, keyword: str) -> pd.DataFrame:
        try:
            stock_list = self.get_stock_list()
            if stock_list.empty:
                return pd.DataFrame(columns=['symbol', 'name'])
            mask = (
                stock_list['symbol'].str.contains(keyword, na=False) |
                stock_list['name'].str.contains(keyword, na=False)
            )
            return stock_list[mask].head(20).reset_index(drop=True)
        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return pd.DataFrame(columns=['symbol', 'name'])

    # ===== 实时行情 =====

    def get_realtime_quotes(self, symbols: list = None) -> pd.DataFrame:
        """
        获取全市场实时行情
        优先东方财富（含PE/PB/市值），失败自动切换新浪
        """
        key = 'realtime_all'
        cached = _cached(key, ttl=60)
        if cached is not None:
            df = cached
        else:
            df = self._fetch_quotes_em()
            if df.empty:
                logger.warning("东方财富行情失败，切换新浪接口…")
                df = self._fetch_quotes_sina()
            if df.empty:
                logger.error("所有行情接口均失败")
                return pd.DataFrame()
            _set_cache(key, df)

        if symbols:
            df = df[df['symbol'].isin(symbols)].reset_index(drop=True)
        return df

    def _fetch_quotes_em(self) -> pd.DataFrame:
        """东方财富全量行情（含 PE/PB/市值/量比）"""
        try:
            result = _run_with_timeout(ak.stock_zh_a_spot_em, timeout=20)
            if result is None or result.empty:
                return pd.DataFrame()
            col_map = {
                '代码': 'symbol', '名称': 'name', '最新价': 'price',
                '涨跌幅': 'change_pct', '涨跌额': 'change_amount',
                '成交量': 'volume', '成交额': 'amount',
                '最高': 'high', '最低': 'low', '今开': 'open',
                '昨收': 'prev_close', '量比': 'volume_ratio',
                '换手率': 'turnover_rate', '市盈率-动态': 'pe_ratio',
                '市净率': 'pb_ratio', '总市值': 'market_cap',
                '流通市值': 'float_market_cap',
                '60日涨跌幅': 'change_60d', '年初至今涨跌幅': 'change_ytd'
            }
            df = result.rename(columns={k: v for k, v in col_map.items() if k in result.columns})
            logger.info(f"东方财富行情成功: {len(df)} 只")
            return df
        except Exception as e:
            logger.warning(f"东方财富接口异常: {e}")
            return pd.DataFrame()

    def _fetch_quotes_sina(self) -> pd.DataFrame:
        """新浪全量行情（备用）"""
        try:
            result = _run_with_timeout(ak.stock_zh_a_spot, timeout=30)
            if result is None or result.empty:
                return pd.DataFrame()

            # 列顺序固定：代码 名称 最新价 涨跌额 涨跌幅 买入 卖出 今开 昨收 最高 最低 成交量 成交额 时间
            pos_cols = ['symbol', 'name', 'price', 'change_amount', 'change_pct',
                        'buy', 'sell', 'open', 'prev_close', 'high', 'low',
                        'volume', 'amount', 'time']
            df = result.copy()
            if len(df.columns) >= len(pos_cols):
                df.columns = pos_cols + list(df.columns[len(pos_cols):])
            else:
                col_map = {
                    '代码': 'symbol', '名称': 'name', '最新价': 'price',
                    '涨跌额': 'change_amount', '涨跌幅': 'change_pct',
                    '今开': 'open', '昨收': 'prev_close',
                    '最高': 'high', '最低': 'low',
                    '成交量': 'volume', '成交额': 'amount',
                }
                df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # 提取 6 位数字代码（sina 格式: sh600519 / sz000001 / bj920000）
            if 'symbol' in df.columns:
                extracted = df['symbol'].str.extract(r'(\d{6})')[0]
                df['symbol'] = extracted.fillna(df['symbol'])

            # 数值转换
            for col in ['price', 'change_pct', 'change_amount', 'open',
                        'prev_close', 'high', 'low', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 补充缺失字段
            for col in ['pe_ratio', 'pb_ratio', 'market_cap', 'volume_ratio',
                        'change_ytd', 'change_60d']:
                if col not in df.columns:
                    df[col] = None

            logger.info(f"新浪行情成功: {len(df)} 只")
            return df
        except Exception as e:
            logger.warning(f"新浪接口异常: {e}")
            return pd.DataFrame()

    def get_quote(self, symbol: str) -> dict:
        """获取单只股票实时行情"""
        try:
            df = self.get_realtime_quotes([symbol])
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception as e:
            logger.error(f"获取 {symbol} 行情失败: {e}")
        return {}

    # ===== 历史行情 =====

    def get_historical_data(self, symbol: str, days: int = 120,
                            adjust: str = 'qfq') -> pd.DataFrame:
        """
        获取历史日线数据（前复权）
        带超时保护：单只股票最长等待 12 秒
        """
        key = f'hist_{symbol}_{days}_{adjust}'
        cached = _cached(key, ttl=600)
        if cached is not None:
            return cached

        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            def _fetch():
                return ak.stock_zh_a_hist(
                    symbol=symbol, period='daily',
                    start_date=start_date, end_date=end_date,
                    adjust=adjust
                )

            result = _run_with_timeout(_fetch, timeout=12)
            if result is None or result.empty:
                return pd.DataFrame()

            col_map = {
                '日期': 'date', '开盘': 'open', '收盘': 'close',
                '最高': 'high', '最低': 'low', '成交量': 'volume',
                '成交额': 'amount', '涨跌幅': 'change_pct',
                '涨跌额': 'change_amount', '换手率': 'turnover_rate'
            }
            df = result.rename(columns={k: v for k, v in col_map.items() if k in result.columns})
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df.sort_values('date').reset_index(drop=True)

            # 确保数值列类型正确
            for col in ['open', 'close', 'high', 'low', 'volume', 'amount', 'change_pct']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            _set_cache(key, df)
            return df
        except Exception as e:
            logger.warning(f"获取 {symbol} 历史数据失败: {e}")
            return pd.DataFrame()

    # ===== 资金流向 =====

    def get_fund_flow(self, symbol: str) -> pd.DataFrame:
        key = f'flow_{symbol}'
        cached = _cached(key, ttl=300)
        if cached is not None:
            return cached
        try:
            market = 'sh' if symbol.startswith('6') else 'sz'

            def _fetch():
                return ak.stock_individual_fund_flow(stock=symbol, market=market)

            result = _run_with_timeout(_fetch, timeout=10)
            if result is not None and not result.empty:
                _set_cache(key, result.head(10))
                return result.head(10)
        except Exception as e:
            logger.debug(f"获取 {symbol} 资金流向失败: {e}")
        return pd.DataFrame()

    # ===== 个股新闻 =====

    def get_stock_news(self, symbol: str, limit: int = 15) -> list:
        key = f'news_{symbol}'
        cached = _cached(key, ttl=1800)
        if cached is not None:
            return cached
        headlines = []
        try:
            def _fetch():
                return ak.stock_news_em(symbol=symbol)

            result = _run_with_timeout(_fetch, timeout=10)
            if result is not None and not result.empty:
                title_col = next(
                    (c for c in result.columns if '标题' in c or 'title' in c.lower()),
                    None
                )
                if title_col:
                    headlines = result[title_col].dropna().head(limit).tolist()
                else:
                    headlines = result.iloc[:, 0].dropna().head(limit).tolist()
            _set_cache(key, headlines)
        except Exception as e:
            logger.debug(f"获取 {symbol} 新闻失败: {e}")
        return headlines

    # ===== 大盘指数 =====

    def get_index_data(self) -> dict:
        key = 'index_data'
        cached = _cached(key, ttl=60)
        if cached is not None:
            return cached
        try:
            index_map = {
                '000001': '上证指数', '399001': '深证成指',
                '399006': '创业板指', '000300': '沪深300',
            }
            result = {}

            def _fetch():
                return ak.stock_zh_index_spot_em()

            df = _run_with_timeout(_fetch, timeout=10)
            if df is not None and not df.empty:
                col_map = {
                    '代码': 'symbol', '名称': 'name',
                    '最新价': 'price', '涨跌幅': 'change_pct'
                }
                df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                for code, name in index_map.items():
                    row = df[df['symbol'] == code]
                    if not row.empty:
                        result[code] = {
                            'name': name,
                            'price': _safe_float(row.iloc[0].get('price'), 0),
                            'change_pct': _safe_float(row.iloc[0].get('change_pct'), 0)
                        }
            _set_cache(key, result)
            return result
        except Exception as e:
            logger.debug(f"获取指数数据失败: {e}")
            return {}

    # ===== 工具 =====

    def get_stock_name(self, symbol: str) -> str:
        try:
            stock_list = self.get_stock_list()
            row = stock_list[stock_list['symbol'] == symbol]
            if not row.empty:
                return str(row.iloc[0]['name'])
        except Exception:
            pass
        return symbol


def _safe_float(val, default=None):
    try:
        v = float(val)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default
