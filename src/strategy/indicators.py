"""
技术指标计算模块
纯 pandas/numpy 实现，无需安装 TA-Lib
包含：MA、EMA、MACD、RSI、布林带、KDJ、量比等
"""
import numpy as np
import pandas as pd


# ===== 基础指标 =====

def ma(series: pd.Series, period: int) -> pd.Series:
    """简单移动平均"""
    return series.rolling(window=period, min_periods=1).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """指数移动平均"""
    return series.ewm(span=period, adjust=False).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD 指标
    返回: (DIF线, DEA信号线, MACD柱)
    """
    dif = ema(series, fast) - ema(series, slow)
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI 相对强弱指标"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger_bands(series: pd.Series, period: int = 20,
                    std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """布林带：返回 (上轨, 中轨, 下轨)"""
    mid = ma(series, period)
    std = series.rolling(window=period, min_periods=1).std()
    return mid + std_dev * std, mid, mid - std_dev * std


def kdj(high: pd.Series, low: pd.Series, close: pd.Series,
        n: int = 9, m: int = 3) -> tuple[pd.Series, pd.Series, pd.Series]:
    """KDJ 随机指标：返回 (K, D, J)"""
    lo = low.rolling(window=n, min_periods=1).min()
    hi = high.rolling(window=n, min_periods=1).max()
    denom = (hi - lo).replace(0, np.nan)
    rsv = (close - lo) / denom * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1 / m, adjust=False).mean()
    d = k.ewm(alpha=1 / m, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """量比：当日成交量 / 近N日平均成交量"""
    avg = volume.rolling(window=period, min_periods=1).mean()
    return volume / avg.replace(0, np.nan)


# ===== 批量计算 =====

def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    在 DataFrame 上计算所有常用技术指标
    要求 df 包含 open/high/low/close/volume 列
    任何子指标计算失败都不影响其他指标
    """
    if df is None or df.empty:
        return df

    required = {'close', 'high', 'low', 'volume'}
    if not required.issubset(df.columns):
        return df

    n = len(df)
    if n < 5:
        return df

    df = df.copy()

    # 确保数值类型
    for col in ['close', 'high', 'low', 'open', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 去掉全 NaN 的行
    df = df.dropna(subset=['close'])
    if df.empty:
        return df

    close = df['close']
    high = df['high']
    low = df['low']
    vol = df['volume'].fillna(0)

    # 均线（min_periods=1 保证不会全 NaN）
    try:
        df['ma5'] = ma(close, 5)
        df['ma10'] = ma(close, 10)
        df['ma20'] = ma(close, 20)
        df['ma60'] = ma(close, 60)
    except Exception:
        pass

    # MACD（至少需要 26 根 K 线）
    try:
        if len(df) >= 26:
            df['dif'], df['dea'], df['macd_hist'] = macd(close)
    except Exception:
        pass

    # RSI
    try:
        if len(df) >= 15:
            df['rsi14'] = rsi(close, 14)
    except Exception:
        pass

    # 布林带
    try:
        if len(df) >= 20:
            df['bb_upper'], df['bb_mid'], df['bb_lower'] = bollinger_bands(close)
    except Exception:
        pass

    # KDJ
    try:
        if len(df) >= 9:
            df['k'], df['d'], df['j'] = kdj(high, low, close)
    except Exception:
        pass

    # 量比
    try:
        df['vol_ratio'] = volume_ratio(vol)
    except Exception:
        pass

    return df


# ===== 交叉信号检测 =====

def is_golden_cross(fast: pd.Series, slow: pd.Series) -> bool:
    """检测金叉（快线上穿慢线）"""
    if len(fast) < 2 or len(slow) < 2:
        return False
    prev = fast.iloc[-2] - slow.iloc[-2]
    curr = fast.iloc[-1] - slow.iloc[-1]
    return (prev <= 0) and (curr > 0)


def is_dead_cross(fast: pd.Series, slow: pd.Series) -> bool:
    """检测死叉（快线下穿慢线）"""
    if len(fast) < 2 or len(slow) < 2:
        return False
    prev = fast.iloc[-2] - slow.iloc[-2]
    curr = fast.iloc[-1] - slow.iloc[-1]
    return (prev >= 0) and (curr < 0)


def is_top_divergence(price: pd.Series, indicator: pd.Series, lookback: int = 20) -> bool:
    """
    检测顶背离：价格创新高但指标未创新高（看跌信号）
    """
    if len(price) < lookback * 2:
        return False
    recent_price = price.iloc[-lookback:]
    prev_price = price.iloc[-lookback * 2: -lookback]
    recent_ind = indicator.iloc[-lookback:]
    prev_ind = indicator.iloc[-lookback * 2: -lookback]

    if recent_price.empty or prev_price.empty:
        return False

    price_new_high = recent_price.max() > prev_price.max()
    ind_no_new_high = recent_ind.max() < prev_ind.max()
    return price_new_high and ind_no_new_high


def ma_slope_up(series: pd.Series, window: int = 10) -> bool:
    """判断均线是否向上倾斜"""
    if len(series) < window:
        return False
    valid = series.dropna()
    if len(valid) < window:
        return False
    return valid.iloc[-1] > valid.iloc[-window]
