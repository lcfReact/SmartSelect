"""
信号引擎 - 尾盘选股策略（次日冲高卖出）

评分体系（技术面主导）：
  基本面权重 0.15 —— 短线操作，基本面仅作风险过滤
  技术面权重 0.85 —— 均线多头 + MACD + 量比 + 换手 + 位置

技术面 6 个维度：
  1. 价格站上 MA60（硬性条件，趋势向上）
  2. 均线多头排列（MA5 > MA10 > MA20，短期动能）
  3. MACD 金叉/多头（买点确认）
  4. RSI 适中区间（40-70，健康状态）
  5. 量比放大（≥1.5，资金介入）
  6. K 线强势（收盘价接近当日最高价）

止盈止损（尾盘超短线策略）：
  目标涨幅：+4%（3-5% 中值）
  止损幅度：-4%（3-5% 中值）
"""
import logging
import math

import pandas as pd

from .indicators import (
    calculate_all, is_golden_cross, is_dead_cross,
    is_top_divergence, ma_slope_up
)

logger = logging.getLogger(__name__)

# ===== 评分权重（技术面主导）=====
FUNDAMENTAL_WEIGHT = 0.15
TECHNICAL_WEIGHT   = 0.85

# ===== 尾盘策略止盈止损（次日冲高）=====
DEFAULT_TAKE_PROFIT_PCT = 4.0   # 目标 +4%
DEFAULT_STOP_LOSS_PCT   = 4.0   # 止损 -4%


class SignalEngine:
    def __init__(self, config: dict = None):
        self.config = config or self._default_config()

    def _default_config(self) -> dict:
        return {
            "fundamental": {
                "max_pe_ratio_multiplier": 80,   # 超短线放宽 PE 限制
            },
            "technical": {
                "rsi_min": 40,
                "rsi_max": 75,
                "volume_increase_pct": 50,        # 量比要求更高
            },
            "risk": {
                "stop_loss_pct":    DEFAULT_STOP_LOSS_PCT,
                "take_profit_pct":  DEFAULT_TAKE_PROFIT_PCT,
                "max_position_pct": 15,
            }
        }

    # ===== 基本面评分（仅作风险过滤，权重 0.15）=====

    def score_fundamental(self, quote: dict) -> float:
        """
        超短线策略基本面评分（0-100）
        主要用途：过滤亏损股、高风险股，不做精细估值
        """
        score = 60.0  # 基础分更高，减少基本面对短线的干扰

        pe         = _safe_float(quote.get('pe_ratio'))
        pb         = _safe_float(quote.get('pb_ratio'))
        market_cap = _safe_float(quote.get('market_cap'))

        # PE：仅排除严重亏损或极度高估
        if pe is not None:
            if pe < 0:
                score -= 20   # 亏损股，风险较高
            elif pe > 150:
                score -= 10   # 极度高估
            elif 8 <= pe <= 60:
                score += 10   # 合理区间小幅加分

        # PB：仅过滤极端异常
        if pb is not None and pb > 0:
            if pb < 1.5:
                score += 8
            elif pb > 15:
                score -= 8

        # 市值：超短线偏好中小盘（弹性更好）
        if market_cap is not None:
            cap_b = market_cap / 1e8
            if 30 <= cap_b <= 200:
                score += 10   # 中小盘弹性最好
            elif 200 < cap_b <= 500:
                score += 5
            elif cap_b < 15:
                score -= 10   # 超小盘流动性差

        return max(0.0, min(100.0, score))

    # ===== 技术面评分（核心，权重 0.85）=====

    def score_technical(self, hist_df: pd.DataFrame,
                        quote: dict = None) -> tuple:
        """
        尾盘策略技术面评分（0-100）
        6 个维度评分 + 技术形态计数（用于信号生成）
        返回: (score, details_dict)
        """
        score = 40.0   # 基础分
        details = {
            'ma5': None, 'ma10': None, 'ma20': None, 'ma60': None,
            'rsi': None, 'vol_ratio': None,
            'dif': None, 'dea': None,
            'macd_signal': 'neutral',
            'golden_cross': False, 'dead_cross': False,
            'top_divergence': False, 'ma60_up': False,
            # 技术形态计数（用于 generate_signal 判断是否 ≥ 2 项达标）
            'pattern_count': 0,
            'pattern_names': [],
        }

        if hist_df is None or hist_df.empty or len(hist_df) < 20:
            return score, details

        try:
            df = calculate_all(hist_df)
            if df is None or df.empty:
                return score, details

            latest     = df.iloc[-1]
            close_s    = df['close']
            curr_price = float(latest['close'])
            day_high   = float(latest.get('high', curr_price))
            day_low    = float(latest.get('low', curr_price))

            # 读取均线值
            details['ma5']  = _safe_float(latest.get('ma5'))
            details['ma10'] = _safe_float(latest.get('ma10'))
            details['ma20'] = _safe_float(latest.get('ma20'))
            details['ma60'] = _safe_float(latest.get('ma60'))
            details['rsi']  = _safe_float(latest.get('rsi14'))
            details['dif']  = _safe_float(latest.get('dif'))
            details['dea']  = _safe_float(latest.get('dea'))

            # ── 维度1：价格站上 MA60（尾盘策略核心条件，+20/-30）──
            ma60 = details['ma60']
            if ma60 and math.isfinite(ma60):
                if curr_price >= ma60:
                    score += 20
                    details['pattern_count'] += 1
                    details['pattern_names'].append('站上MA60')
                else:
                    score -= 30  # 不在 MA60 上方，大幅扣分

            # ── 维度2：均线多头排列 MA5 > MA10 > MA20（+20 / 局部+10）──
            ma5  = details['ma5']
            ma10 = details['ma10']
            ma20 = details['ma20']
            if ma5 and ma10 and ma20:
                if ma5 > ma10 > ma20 and curr_price > ma5:
                    # 完整多头排列 + 价格站上 MA5
                    score += 20
                    details['pattern_count'] += 1
                    details['pattern_names'].append('均线多头排列')
                elif ma5 > ma10 and curr_price > ma10:
                    # 短期多头（MA5/MA10）
                    score += 10
                    details['pattern_names'].append('短期多头')
                elif curr_price < ma20:
                    score -= 10  # 价格跌破 MA20，弱势

            # ── 维度3：MACD 信号（+20 金叉 / +10 多头 / -15 死叉）──
            if 'dif' in df.columns and 'dea' in df.columns:
                dif_s = df['dif'].dropna()
                dea_s = df['dea'].dropna()
                if len(dif_s) >= 2:
                    golden = is_golden_cross(dif_s, dea_s)
                    dead   = is_dead_cross(dif_s, dea_s)
                    details['golden_cross'] = golden
                    details['dead_cross']   = dead

                    if golden:
                        score += 20
                        details['macd_signal'] = 'golden_cross'
                        details['pattern_count'] += 1
                        details['pattern_names'].append('MACD金叉')
                    elif dead:
                        score -= 15
                        details['macd_signal'] = 'dead_cross'
                    elif details['dif'] and details['dea']:
                        if details['dif'] > details['dea']:
                            score += 10
                            details['macd_signal'] = 'bullish'
                            details['pattern_names'].append('MACD多头')
                        else:
                            score -= 5
                            details['macd_signal'] = 'bearish'

            # ── 维度4：RSI（尾盘强势股 40-75 最佳）──
            rsi_val = details['rsi']
            if rsi_val and math.isfinite(rsi_val):
                if 45 <= rsi_val <= 70:
                    score += 10   # 健康区间
                elif 70 < rsi_val <= 80:
                    score += 5    # 偏强但未超买
                elif rsi_val > 80:
                    score -= 10   # 超买，次日冲高后容易回落
                elif rsi_val < 30:
                    score -= 5    # 弱势

            # ── 维度5：量比验证（已在预筛中要求≥1.5，这里奖励更高量比）──
            vr = details.get('vol_ratio')
            if not vr:
                vr = _safe_float(quote.get('volume_ratio') if quote else None)
            details['vol_ratio'] = vr
            if vr and math.isfinite(vr):
                if vr >= 3.0:
                    score += 12   # 大量介入
                    if vr not in [p for p in details['pattern_names'] if 'MA' in str(p)]:
                        details['pattern_count'] += 1
                        details['pattern_names'].append(f'大量{vr:.1f}X')
                elif vr >= 2.0:
                    score += 8
                elif vr >= 1.5:
                    score += 4
                elif vr < 1.0:
                    score -= 8    # 缩量，不符合尾盘策略

            # ── 维度6：K 线强势（收盘接近当日最高价，说明尾盘强势）──
            if day_high > day_low:
                close_position = (curr_price - day_low) / (day_high - day_low)
                if close_position >= 0.80:
                    score += 10   # 收盘在日内高位 80% 以上
                    details['pattern_count'] += 1
                    details['pattern_names'].append('尾盘强势K线')
                elif close_position >= 0.60:
                    score += 5
                elif close_position < 0.30:
                    score -= 8    # 收盘在低位，弱势

            # ── MA60 方向 ──
            if len(df) >= 70 and 'ma60' in df.columns:
                details['ma60_up'] = ma_slope_up(df['ma60'], 10)
                if details['ma60_up']:
                    score += 5
                else:
                    score -= 3

            # ── 顶背离（看跌，扣分）──
            if 'dif' in df.columns:
                dif_clean = df['dif'].dropna()
                if len(dif_clean) >= 40:
                    details['top_divergence'] = is_top_divergence(close_s, dif_clean)
                    if details['top_divergence']:
                        score -= 15

        except Exception as e:
            logger.warning(f"尾盘技术面评分异常: {e}")

        return max(0.0, min(100.0, score)), details

    # ===== 综合分析 =====

    def analyze(self, symbol: str, name: str,
                quote: dict, hist_df: pd.DataFrame):
        """
        综合分析，返回评分结果字典（无论是否触发信号）
        """
        try:
            price = _safe_float(quote.get('price'))
            if not price or price <= 0:
                return None

            f_score = self.score_fundamental(quote)
            t_score, tech = self.score_technical(hist_df, quote)
            total = f_score * FUNDAMENTAL_WEIGHT + t_score * TECHNICAL_WEIGHT

            rec = _recommendation(total)

            change_pct = _safe_float(quote.get('change_pct'), 0)

            return {
                'symbol':            symbol,
                'name':              name,
                'price':             price,
                'change_pct':        change_pct,
                'fundamental_score': round(f_score, 1),
                'technical_score':   round(t_score, 1),
                'total_score':       round(total, 1),
                'recommendation':    rec,
                'ma5':               tech.get('ma5'),
                'ma10':              tech.get('ma10'),
                'ma20':              tech.get('ma20'),
                'ma60':              tech.get('ma60'),
                'rsi':               tech.get('rsi'),
                'volume_ratio':      tech.get('vol_ratio') or _safe_float(quote.get('volume_ratio')),
                'turnover_rate':     _safe_float(quote.get('turnover_rate')),
                'macd_signal':       tech.get('macd_signal', 'neutral'),
                'pe_ratio':          _safe_float(quote.get('pe_ratio')),
                'pb_ratio':          _safe_float(quote.get('pb_ratio')),
                'market_cap':        _safe_float(quote.get('market_cap')),
                'pattern_count':     tech.get('pattern_count', 0),
                'pattern_names':     tech.get('pattern_names', []),
                '_tech':             tech,
            }
        except Exception as e:
            logger.error(f"analyze {symbol} 异常: {e}")
            return None

    def generate_signal(self, symbol: str, name: str,
                        quote: dict, hist_df: pd.DataFrame):
        """
        生成买入/卖出信号（满足尾盘条件才返回）
        
        买入条件（尾盘策略，全部满足）：
          ① total_score >= 62
          ② 至少满足 2 项技术形态
          ③ MACD 不是死叉
          ④ 无顶背离
        
        卖出条件（持仓预警，任一满足）：
          ① MACD 死叉
          ② RSI 超买（> 80）且顶背离
        """
        result = self.analyze(symbol, name, quote, hist_df)
        if result is None:
            return None

        tech    = result.pop('_tech', {})
        total   = result['total_score']
        price   = result['price']
        pattern = result.get('pattern_count', 0)

        reasons = []
        buy_score = 0.0
        sell_score = 0.0

        # ── 买入条件打分 ──
        if total >= 62:
            buy_score += 1

        # 核心：技术形态 ≥ 2 项（尾盘策略要求）
        if pattern >= 2:
            buy_score += 2
            reasons += result.get('pattern_names', [])[:3]
        elif pattern == 1:
            buy_score += 0.5

        # MACD 状态
        if tech.get('golden_cross'):
            buy_score += 1
        if tech.get('dead_cross'):
            buy_score -= 3  # 死叉直接阻止买入

        # 量比高
        vr = tech.get('vol_ratio') or 0
        if vr >= 2.0:
            buy_score += 0.5
            reasons.append(f"量比{vr:.1f}X")

        change_pct = result.get('change_pct', 0)
        if 2.0 <= change_pct <= 7.0:
            reasons.append(f"涨幅{change_pct:.1f}%")
        else:
            buy_score -= 2  # 涨幅不符合尾盘条件

        # 顶背离
        if tech.get('top_divergence'):
            buy_score -= 2
            reasons.append("⚠顶背离")

        # ── 卖出条件 ──
        if tech.get('dead_cross'):
            sell_score += 2
            reasons.append("MACD死叉")

        rsi_val = tech.get('rsi')
        if rsi_val and rsi_val > 80:
            sell_score += 1
            reasons.append(f"RSI超买{rsi_val:.0f}")

        if tech.get('top_divergence'):
            sell_score += 2

        # ── 判断信号类型 ──
        signal_type = None
        if buy_score >= 2.5 and total >= 62:
            signal_type = 'buy'
        elif sell_score >= 2.0:
            signal_type = 'sell'

        if not signal_type:
            return None

        # ── 止损止盈（尾盘超短线：+4% / -4%）──
        cfg_risk = self.config.get('risk', {})
        sl_pct = cfg_risk.get('stop_loss_pct',   DEFAULT_STOP_LOSS_PCT)   / 100
        tp_pct = cfg_risk.get('take_profit_pct', DEFAULT_TAKE_PROFIT_PCT) / 100
        stop_loss    = round(price * (1 - sl_pct), 2)
        target_price = round(price * (1 + tp_pct), 2)

        # 信号强度（1-5星）
        strength = 1
        if total >= 85:
            strength = 5
        elif total >= 78:
            strength = 4
        elif total >= 70:
            strength = 3
        elif total >= 63:
            strength = 2

        signal = result.copy()
        signal.update({
            'signal_type':    signal_type,
            'target_price':   target_price,
            'stop_loss':      stop_loss,
            'reason':         '、'.join(reasons) or '尾盘强势',
            'signal_strength': strength,
        })
        return signal

    def check_position_alerts(self, position: dict, current_price: float) -> list:
        """检测持仓是否触发止盈/止损提醒"""
        alerts = []
        buy_price = position.get('buy_price', 0)
        if not buy_price or not current_price:
            return alerts

        target     = position.get('target_price')
        stop       = position.get('stop_loss')
        symbol     = position.get('symbol', '')
        name       = position.get('name', symbol)
        profit_pct = (current_price - buy_price) / buy_price * 100

        if stop and current_price <= stop:
            alerts.append({
                'type': 'stop_loss', 'severity': 'critical',
                'symbol': symbol, 'name': name,
                'msg': f"【止损预警】{name}({symbol}) 触及止损价 {stop:.2f}！"
                       f"当前价 {current_price:.2f}，浮亏 {profit_pct:.1f}%，请立即操作！"
            })
        elif stop and current_price <= stop * 1.015:
            alerts.append({
                'type': 'near_stop', 'severity': 'warning',
                'symbol': symbol, 'name': name,
                'msg': f"【接近止损】{name}({symbol}) 距止损仅剩 {(current_price/stop-1)*100:.1f}%"
            })

        if target and current_price >= target:
            alerts.append({
                'type': 'take_profit', 'severity': 'info',
                'symbol': symbol, 'name': name,
                'msg': f"【达到目标价】{name}({symbol}) 已达目标价 {target:.2f}！"
                       f"浮盈 +{profit_pct:.1f}%，次日冲高时考虑止盈。"
            })
        elif profit_pct >= 4 and (not target or current_price < target):
            alerts.append({
                'type': 'high_profit', 'severity': 'info',
                'symbol': symbol, 'name': name,
                'msg': f"【浮盈提示】{name}({symbol}) 浮盈 +{profit_pct:.1f}%，可考虑止盈。"
            })
        return alerts


# ===== 工具函数 =====

def _safe_float(val, default=None):
    try:
        v = float(val)
        if v != v:   # NaN
            return default
        return v
    except (TypeError, ValueError):
        return default


def _recommendation(total: float) -> str:
    """尾盘策略推荐级别（阈值下调，技术面权重高分更易达到）"""
    if total >= 82:
        return 'strong_buy'
    elif total >= 65:
        return 'buy'
    elif total >= 48:
        return 'hold'
    elif total >= 32:
        return 'sell'
    return 'strong_sell'
