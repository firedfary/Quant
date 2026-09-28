"""
策略三：核心资产多资产 ETF 动量轮动策略
Multi-Asset Core ETF Momentum Rotation Strategy (Dual Momentum)
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from config import LOT_SIZE
from core.account import Account
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("MomentumRotation")

class MomentumRotationStrategy(BaseStrategy):
    """
    经典双动量轮动策略 (Dual Momentum Asset Allocation)：
    - 标的池覆盖大盘股票(沪深300)、全球科技(纳指ETF)、大宗避险(黄金ETF)、稳健防御(红利ETF)
    - 动量评分 = 近 20 个交易日收益率 / 年化波动率 (夏普型风险调整动量)
    - 进攻规则：在表现为正的资产中，持有动量排名第一的最强资产
    - 防御规则：当所有标的 20 日动量均为负（系统性熊市/普跌）时，主动清仓避险，100% 持有现金防御
    """
    def __init__(
        self,
        symbols: List[str] = ["513100", "510300", "518880", "510880"],
        lookback_period: int = 20,
        target_allocation: float = 0.55  # 胜出资产的目标持仓权重 (55%，适配风控60%单标的红线)
    ):
        super().__init__(name="ETF_Momentum_Rotation", symbols=symbols)
        self.lookback_period = lookback_period
        self.target_allocation = target_allocation

    def compute_momentum_scores(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """计算各个标的的风险调整动量得分"""
        scores = {}
        for sym in self.symbols:
            if sym not in data_dict or len(data_dict[sym]) < self.lookback_period + 5:
                continue

            df = data_dict[sym]
            close_series = df["close"]
            
            # 20日累计收益率
            ret_20 = (close_series.iloc[-1] / close_series.iloc[-self.lookback_period] - 1.0)
            
            # 近20日日收益率序列的标准差 (波动率)
            daily_returns = close_series.tail(self.lookback_period).pct_change().dropna()
            vol_20 = daily_returns.std() * np.sqrt(250) if len(daily_returns) > 1 else 0.15

            # 风险调整动量评分 (类似信息比率)
            score = ret_20 / (vol_20 + 1e-4)
            scores[sym] = round(score, 4)

        return scores

    def generate_signals(
        self, 
        data_dict: Dict[str, pd.DataFrame], 
        account: Account,
        realtime_quotes: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Signal]:
        signals = []
        scores = self.compute_momentum_scores(data_dict)
        if not scores:
            return signals

        # 按动量得分由高到低排序
        sorted_symbols = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_symbol, best_score = sorted_symbols[0]
        logger.info(f"动量轮动评分排名: {sorted_symbols}")

        current_holdings = [sym for sym, pos in account.positions.items() if pos.total_qty > 0]

        # 1. 防御机制：如果动量第一名也为负，全市场避险，卖出所有持仓，空仓观望
        if best_score <= 0.0:
            logger.info("全市场动量转负，触发空仓避险防御机制！")
            for sym in current_holdings:
                pos = account.positions[sym]
                if pos.available_qty > 0:
                    curr_price = realtime_quotes[sym]["price"] if (realtime_quotes and sym in realtime_quotes) else pos.current_price
                    signals.append(Signal(
                        symbol=sym,
                        action="SELL",
                        price=curr_price,
                        qty=pos.available_qty,
                        strategy_name=self.name,
                        reason=f"全市场动量均为负，清仓避险防御 (当前最佳 {best_symbol} 动量得分仅 {best_score})"
                    ))
            return signals

        # 2. 轮动调仓逻辑：
        # 若当前持仓不是最优标的，则卖出旧标的，买入最优标的
        for sym in current_holdings:
            if sym != best_symbol:
                pos = account.positions[sym]
                if pos.available_qty > 0:
                    curr_price = realtime_quotes[sym]["price"] if (realtime_quotes and sym in realtime_quotes) else pos.current_price
                    signals.append(Signal(
                        symbol=sym,
                        action="SELL",
                        price=curr_price,
                        qty=pos.available_qty,
                        strategy_name=self.name,
                        reason=f"动量轮动换仓: 卖出弱势标的 {sym}，换入强势龙头 {best_symbol}"
                    ))

        # 买入/加仓当前最强标的
        best_price = realtime_quotes[best_symbol]["price"] if (realtime_quotes and best_symbol in realtime_quotes) else float(data_dict[best_symbol].iloc[-1]["close"])
        target_equity_allocation = account.total_equity * self.target_allocation
        curr_allocated_mv = account.positions[best_symbol].market_value if best_symbol in account.positions else 0.0

        if target_equity_allocation > curr_allocated_mv:
            needed_budget = min(account.cash, target_equity_allocation - curr_allocated_mv)
            buy_qty = int(needed_budget // (best_price * LOT_SIZE)) * LOT_SIZE
            if buy_qty > 0:
                signals.append(Signal(
                    symbol=best_symbol,
                    action="BUY",
                    price=best_price,
                    qty=buy_qty,
                    strategy_name=self.name,
                    reason=f"动量排名第一 (评分: {best_score:.2f})，买入强势龙头资产"
                ))

        return signals
