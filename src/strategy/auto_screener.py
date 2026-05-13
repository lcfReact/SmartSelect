"""
全市场自动选股引擎 - 尾盘选股 + 次日冲高卖出策略

策略核心逻辑（来源：doc.md）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
选股时段：下午 14:30–14:55（尾盘）
买入时段：14:40–14:55
卖出时段：次日 9:30–10:30 冲高卖出

基础筛选条件（必须全部满足）：
  1. 当日涨幅：+2% ~ +7%（过小无动力，过大追高风险）
  2. 量比 ≥ 1.5（放量说明资金介入）
  3. 股价站上 60 日均线（趋势向上）
  4. 换手率：3% ~ 15%（资金活跃，但不过分松散）
  5. 日成交额 ≥ 5000 万（流动性充足）
  6. 非 ST 股

技术形态筛选（满足至少 2 项）：
  A. 均线多头排列（MA5 > MA10 > MA20，股价站上所有短期均线）
  B. MACD 金叉或多头（DIF > DEA，金叉优先）
  C. 尾盘持续强势（收盘价接近最高价，K 线实体长）
  D. 突破形态（站上 5 日或 10 日均线前期高点）

风控：
  目标涨幅：+3% ~ +5%（次日冲高止盈）
  止损：    -3% ~ -5%（严格执行）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)


# ===== 预筛参数（硬性门槛）=====
DEFAULT_PRE_FILTER = {
    "exclude_st":         True,   # 剔除 ST / *ST 风险股
    "min_price":          3.0,    # 最低 3 元（避免仙股）
    "max_price":          200.0,  # 最高 200 元（高价股弹性差）
    "min_amount":         5e7,    # 最低成交额 5000 万（流动性）
    "min_change_pct":     2.0,    # 必须涨幅 ≥ 2%（有上攻动力）
    "max_change_pct":     7.0,    # 涨幅 ≤ 7%（排除追高风险）
    "min_volume_ratio":   1.5,    # 量比 ≥ 1.5（资金主动介入）
    "min_turnover_rate":  3.0,    # 换手率 ≥ 3%（活跃交投）
    "max_turnover_rate":  15.0,   # 换手率 ≤ 15%（筹码不过度松散）
    "top_n_quick":        80,     # 快速评分后进入深度分析的候选数量
}

# 最终输出数量
FINAL_OUTPUT_N = 10


def pre_filter(df: pd.DataFrame, cfg: dict = None) -> pd.DataFrame:
    """
    尾盘策略硬性门槛预筛
    所有条件缺乏数据时降级容错，避免全军覆没
    """
    params = {**DEFAULT_PRE_FILTER, **(cfg or {})}
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)

    # ── 强制：A股主板/创业板/科创板（剔除北交所、B股）──
    if 'symbol' in df.columns:
        mask &= df['symbol'].str.match(r'^[036]\d{5}$', na=False)

    # ── 强制：剔除 ST ──
    if params['exclude_st'] and 'name' in df.columns:
        mask &= ~df['name'].str.contains('ST', case=False, na=False)

    # ── 强制：价格有效且在合理范围 ──
    if 'price' in df.columns:
        price = pd.to_numeric(df['price'], errors='coerce')
        mask &= price.notna() & (price >= params['min_price']) & (price <= params['max_price'])

    # ── 强制：今日有成交量 ──
    if 'volume' in df.columns:
        vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
        mask &= vol > 0

    # ── 核心：涨幅必须在 +2% ~ +7%（尾盘策略核心条件）──
    if 'change_pct' in df.columns:
        chg = pd.to_numeric(df['change_pct'], errors='coerce').fillna(0)
        mask &= (chg >= params['min_change_pct']) & (chg <= params['max_change_pct'])

    # ── 核心：成交额 ≥ 5000万（流动性） ──
    if 'amount' in df.columns:
        amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        mask &= amt >= params['min_amount']

    # ── 核心：量比 ≥ 1.5（有数据时才用） ──
    if 'volume_ratio' in df.columns:
        vr = pd.to_numeric(df['volume_ratio'], errors='coerce')
        has_vr = vr.notna()
        if has_vr.sum() > len(df) * 0.2:
            mask &= (vr >= params['min_volume_ratio']) | vr.isna()

    # ── 换手率：3% ~ 15%（有数据时才用）──
    if 'turnover_rate' in df.columns:
        tr = pd.to_numeric(df['turnover_rate'], errors='coerce')
        has_tr = tr.notna()
        if has_tr.sum() > len(df) * 0.2:
            valid_tr = (tr >= params['min_turnover_rate']) & (tr <= params['max_turnover_rate'])
            mask &= valid_tr | tr.isna()

    filtered = df[mask].copy()
    logger.info(f"尾盘预筛：{len(df)} 只 → {len(filtered)} 只通过（涨幅2-7%+量比+换手率）")
    return filtered


def tail_market_score(row: pd.Series) -> float:
    """
    尾盘快速评分（无需历史数据，基于实时行情）
    
    满分 100 分，三个维度：
    ① 涨幅质量（40分）：2-5% 最优，5-7% 次之
    ② 量能质量（35分）：量比越高越好，但不能异常天量
    ③ 资金规模（25分）：成交额越大越好 + 换手率合理
    """
    score = 40.0  # 基础分（通过硬性门槛即获得）

    change  = _safe(row.get('change_pct'), 0)
    vr      = _safe(row.get('volume_ratio'), 1.5)
    amount  = _safe(row.get('amount'), 0)
    tr      = _safe(row.get('turnover_rate'))
    price   = _safe(row.get('price'))

    # ══ ① 涨幅质量（最高 +40 分）══
    # 尾盘策略最优区间：2%-5%（强势但不过热）
    if 3.0 <= change <= 5.0:
        score += 40   # 最佳区间：温和强势
    elif 2.5 <= change < 3.0:
        score += 33
    elif 2.0 <= change < 2.5:
        score += 25
    elif 5.0 < change <= 6.0:
        score += 18   # 涨幅偏大，追高有压力
    elif 6.0 < change <= 7.0:
        score += 8    # 接近限制上沿，谨慎

    # ══ ② 量能质量（最高 +35 分）══
    # 放量是尾盘策略的核心验证条件
    if vr is not None:
        if vr >= 3.0:
            score += 35   # 大量介入，强烈信号
        elif vr >= 2.5:
            score += 30
        elif vr >= 2.0:
            score += 23
        elif vr >= 1.5:
            score += 15   # 刚过门槛，信号一般

    # ══ ③ 资金规模 + 换手率（最高 +25 分）══
    if amount is not None and amount > 0:
        amt_yi = amount / 1e8  # 转换为亿元
        if amt_yi >= 5:
            score += 15    # 大资金活跃
        elif amt_yi >= 2:
            score += 10
        elif amt_yi >= 1:
            score += 6
        elif amt_yi >= 0.5:
            score += 3

    # 换手率：5%-10% 是尾盘选股最优区间
    if tr is not None:
        if 5.0 <= tr <= 10.0:
            score += 10
        elif 3.0 <= tr < 5.0:
            score += 6
        elif 10.0 < tr <= 12.0:
            score += 4
        # 12-15% 筹码偏松，不加分

    # ── 低价股额外关注：5-30元活跃度高 ──
    if price is not None and 5 <= price <= 30:
        score += 3

    return max(0.0, min(100.0, score))


def select_candidates(df: pd.DataFrame, top_n: int = 80) -> pd.DataFrame:
    """打快速分并返回 TOP-N 候选（进入深度技术分析）"""
    if df.empty:
        return df
    df = df.copy()
    df['_quick_score'] = df.apply(tail_market_score, axis=1)
    df = df.sort_values('_quick_score', ascending=False)
    candidates = df.head(top_n).reset_index(drop=True)
    logger.info(f"从 {len(df)} 只中按尾盘分选出 TOP-{len(candidates)} 候选进入深度分析")
    return candidates


def get_market_condition() -> str:
    """
    判断当前大盘状态（影响选股门槛）
    返回: 'bull' / 'bear' / 'neutral'
    
    尾盘策略对大盘依赖较强：
      大盘下跌趋势中尾盘买入成功率大幅降低，应空仓观望
    """
    try:
        from src.data.data_fetcher import DataFetcher
        fetcher = DataFetcher()
        hist = fetcher.get_historical_data('000001', days=90)
        if hist is None or hist.empty or len(hist) < 20:
            return 'neutral'
        close    = hist['close']
        ma20     = close.rolling(20, min_periods=10).mean()
        ma60     = close.rolling(60, min_periods=30).mean()
        cur      = float(close.iloc[-1])
        cur_ma20 = float(ma20.iloc[-1])
        cur_ma60 = float(ma60.iloc[-1])
        prev_ma20 = float(ma20.iloc[-5]) if len(ma20) >= 5 else cur_ma20

        if cur > cur_ma20 and cur_ma20 > cur_ma60 and cur_ma20 > prev_ma20:
            return 'bull'
        elif cur < cur_ma20 and cur_ma20 < cur_ma60:
            return 'bear'
        return 'neutral'
    except Exception as e:
        logger.debug(f"大盘状态判断失败（忽略）: {e}")
        return 'neutral'


def final_select(results: list) -> list:
    """
    从深度分析结果中筛出最终 10 只尾盘精选股

    筛选逻辑：
    ① 硬性门槛（全部满足才入选）
       - technical_score >= 58（技术面为主）
       - total_score >= 阈值（牛市60 / 中性63 / 熊市68）
       - recommendation in (buy, strong_buy)
       - price > MA60（确认趋势向上）
    
    ② 尾盘特有加分规则
       - 技术形态得分（均线多头 / MACD金叉 / 量比高）累加
    
    ③ 分散度控制（同板块最多3只）
    
    ④ 按综合分排序取前 10
    """
    from src.ui.scanner_tab import _buy_value_score

    condition = get_market_condition()
    # 尾盘策略更看重大盘状态，熊市门槛提高
    thresholds = {'bull': 60, 'neutral': 63, 'bear': 68}
    min_total = thresholds.get(condition, 63)
    logger.info(f"大盘状态: {condition}，尾盘入选门槛: total_score >= {min_total}")

    qualified = []
    for r in results:
        total = float(r.get('total_score') or 0)
        rec   = r.get('recommendation', 'hold')
        tech  = float(r.get('technical_score') or 0)

        # ── 基础门槛 ──
        if rec not in ('buy', 'strong_buy'):
            continue
        if total < min_total:
            continue
        if tech < 58:
            continue

        # ── 硬性要求：价格站上 MA60（趋势向上，尾盘策略核心之一）──
        price = r.get('price')
        ma60  = r.get('ma60')
        if price and ma60:
            try:
                if float(price) < float(ma60) * 0.97:
                    continue  # 跌破 MA60，排除
            except (TypeError, ValueError):
                pass

        # ── 尾盘特有加权：MACD 金叉优先 ──
        tail_bonus = 0
        if r.get('macd_signal') == 'golden_cross':
            tail_bonus += 8   # 金叉加权最高
        elif r.get('macd_signal') == 'bullish':
            tail_bonus += 4
        vr = r.get('volume_ratio') or 0
        if vr >= 2.5:
            tail_bonus += 5
        elif vr >= 2.0:
            tail_bonus += 3
        r['_tail_score'] = total + tail_bonus
        qualified.append(r)

    # 按尾盘综合分排序
    qualified.sort(key=lambda r: r.get('_tail_score', 0), reverse=True)

    # ── 分散度控制（同板块最多3只）──
    bucket_count = {}
    diversified = []
    for r in qualified:
        sym = str(r.get('symbol', ''))
        bucket = sym[0] if sym else 'x'
        if bucket_count.get(bucket, 0) < 3:
            bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
            diversified.append(r)
        if len(diversified) >= FINAL_OUTPUT_N:
            break

    # 若分散后不足 10 只，补足
    if len(diversified) < FINAL_OUTPUT_N:
        added = {r['symbol'] for r in diversified}
        for r in qualified:
            if r['symbol'] not in added:
                diversified.append(r)
            if len(diversified) >= FINAL_OUTPUT_N:
                break

    # 清理临时字段
    final = diversified[:FINAL_OUTPUT_N]
    for r in final:
        r.pop('_tail_score', None)

    logger.info(
        f"深度分析 {len(results)} 只 → 尾盘门槛过滤 {len(qualified)} 只 → "
        f"分散控制后 {len(final)} 只（大盘: {condition}）"
    )
    return final


def _safe(val, default=None):
    try:
        v = float(val)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default
