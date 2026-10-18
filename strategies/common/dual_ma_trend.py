"""
跨市场经典 EMA 动量双均线趋势跟踪策略
Multi-Market EMA Trend Following Strategy with Dynamic Trailing Stop
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from core.account import Account
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("DualMATrend")

class DualMATrendStrategy(BaseStrategy):
    """
    经典成熟的双均线动量突破系统：
    - 快线 EMA(fast) 上穿 慢线 EMA(slow) 形成金叉买入
    - 快线 EMA(fast) 下穿 慢线 EMA(slow) 形成死叉卖出
    - 结合 ATR (真实波动幅度) 动态追踪止损
    - 支持 A 股 ETF 整手约束与虚拟币小数位下单
    """
    def __init__(
        self, 
        symbols: List[str] = ["510300", "513100"],
        fast_period: int = 10,
        slow_period: int = 30,
        atr_period: int = 14,
        atr_multiplier: float = 2.5,
        pos_ratio: float = 0.45,
        lot_size: Optional[int] = None,
        qty_precision: int = 4
    ):
        super().__init__(name="EMA_Trend_Following", symbols=symbols)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.pos_ratio = pos_ratio
        self.lot_size = lot_size
        self.qty_precision = qty_precision

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算 EMA 均线与 ATR 波动指标"""
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_period, adjust=False).mean()

        # 计算 ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=self.atr_period).mean()

        return df

    def _calc_order_qty(self, price: float, budget: float) -> float:
        """计算买入量"""
        if price <= 0:
            return 0.0
        if self.lot_size and self.lot_size > 0:
            qty = int(budget // (price * self.lot_size)) * self.lot_size
            return float(qty)
        else:
            return round(budget / price, self.qty_precision)

    def generate_signals(
        self, 
        data_dict: Dict[str, pd.DataFrame], 
        account: Account,
        realtime_quotes: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Signal]:
        signals = []

        for symbol in self.symbols:
            if symbol not in data_dict or data_dict[symbol].empty:
                continue

            df = data_dict[symbol]
            if len(df) < self.slow_period + 5:
                continue

            df = self.calculate_indicators(df)
            last_bar = df.iloc[-1]
            prev_bar = df.iloc[-2]

            # 获取最新价格
            if realtime_quotes and symbol in realtime_quotes:
                curr_price = realtime_quotes[symbol]["price"]
            else:
                curr_price = float(last_bar["close"])

            has_pos = symbol in account.positions and account.positions[symbol].total_qty > 0
            pos = account.positions.get(symbol)

            # 金叉判定: 快线上穿慢线
            golden_cross = (prev_bar["ema_fast"] <= prev_bar["ema_slow"]) and (last_bar["ema_fast"] > last_bar["ema_slow"])
            
            # 死叉判定: 快线下穿慢线
            death_cross = (prev_bar["ema_fast"] >= prev_bar["ema_slow"]) and (last_bar["ema_fast"] < last_bar["ema_slow"])

            # 1. 卖出逻辑 (平仓)
            if has_pos and pos and pos.available_qty > 0:
                atr_val = last_bar["atr"] if not np.isnan(last_bar["atr"]) else curr_price * 0.02
                stop_price = pos.cost_price - self.atr_multiplier * atr_val

                # 触及 ATR 追踪止损
                if curr_price < stop_price:
                    signals.append(Signal(
                        symbol=symbol,
                        action="SELL",
                        price=curr_price,
                        qty=pos.available_qty,
                        strategy_name=self.name,
                        reason=f"ATR动态止损离场: 现价 {curr_price:.4f} 跌破止损线 {stop_price:.4f}"
                    ))
                # 均线死叉卖出
                elif death_cross:
                    signals.append(Signal(
                        symbol=symbol,
                        action="SELL",
                        price=curr_price,
                        qty=pos.available_qty,
                        strategy_name=self.name,
                        reason=f"EMA均线死叉卖出 (EMA{self.fast_period}下穿EMA{self.slow_period})"
                    ))

            # 2. 买入逻辑 (开仓/加仓)
            elif not has_pos and golden_cross:
                target_budget = account.cash * self.pos_ratio
                buy_qty = self._calc_order_qty(curr_price, target_budget)
                if buy_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="BUY",
                        price=curr_price,
                        qty=buy_qty,
                        strategy_name=self.name,
                        reason=f"EMA均线金叉买入 (EMA{self.fast_period}上穿EMA{self.slow_period}, 趋势向好)"
                    ))

        return signals
