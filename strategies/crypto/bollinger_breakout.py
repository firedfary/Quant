"""
加密货币布林带波动率突破策略
Crypto Bollinger Bands Volatility Breakout Strategy
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from core.account import Account
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("BollingerBreakout")

class BollingerBreakoutStrategy(BaseStrategy):
    """
    专为加密货币 7x24 高波动率特性设计的布林带通道突破算法：
    - 中轨 = 20日简单移动平均线 (SMA20)
    - 上轨 = SMA20 + 2.0 * 标准差
    - 下轨 = SMA20 - 2.0 * 标准差
    - 买入信号：收盘价由下向上突破布林线上轨，伴随波动率放大，跟进强势趋势
    - 卖出信号：价格跌破布林中轨（保护性止盈）或跌破下轨（硬性止损）
    """
    def __init__(
        self,
        symbols: List[str] = ["BTCUSDT", "ETHUSDT"],
        period: int = 20,
        std_dev: float = 2.0,
        pos_ratio: float = 0.4,
        qty_precision: int = 4
    ):
        super().__init__(name="Crypto_Bollinger_Breakout", symbols=symbols)
        self.period = period
        self.std_dev = std_dev
        self.pos_ratio = pos_ratio
        self.qty_precision = qty_precision

    def calculate_bollinger_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["mid"] = df["close"].rolling(window=self.period).mean()
        df["std"] = df["close"].rolling(window=self.period).std()
        df["upper"] = df["mid"] + self.std_dev * df["std"]
        df["lower"] = df["mid"] - self.std_dev * df["std"]
        return df

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
            if len(df) < self.period + 5:
                continue

            df = self.calculate_bollinger_bands(df)
            last_bar = df.iloc[-1]
            prev_bar = df.iloc[-2]

            if realtime_quotes and symbol in realtime_quotes:
                curr_price = realtime_quotes[symbol]["price"]
            else:
                curr_price = float(last_bar["close"])

            pos = account.positions.get(symbol)
            has_pos = pos is not None and pos.total_qty > 0

            # 突破判定
            upper_break = (prev_bar["close"] <= prev_bar["upper"]) and (curr_price > last_bar["upper"])
            mid_drop = curr_price < last_bar["mid"]

            # 1. 卖出逻辑 (平仓)
            if has_pos and pos and pos.available_qty > 0:
                if mid_drop:
                    signals.append(Signal(
                        symbol=symbol,
                        action="SELL",
                        price=curr_price,
                        qty=pos.available_qty,
                        strategy_name=self.name,
                        reason=f"跌破布林中轨 ({last_bar['mid']:.2f})，平仓锁定收益"
                    ))

            # 2. 买入逻辑 (突破上轨建仓)
            elif not has_pos and upper_break:
                budget = account.cash * self.pos_ratio
                buy_qty = round(budget / curr_price, self.qty_precision)
                if buy_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="BUY",
                        price=curr_price,
                        qty=buy_qty,
                        strategy_name=self.name,
                        reason=f"强势突破布林线上轨 ({last_bar['upper']:.2f})，跟进右侧趋势"
                    ))

        return signals
