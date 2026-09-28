"""
策略二：自适应 ETF 网格交易策略 (震荡市高胜率套利)
Adaptive ETF Grid Trading Strategy Tailored for 20,000 RMB Capital
"""

from typing import Dict, List, Optional, Any
import pandas as pd
from config import LOT_SIZE
from core.account import Account
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("GridTrading")

class GridTradingStrategy(BaseStrategy):
    """
    针对 20,000 元小本金精细化设计的等比动态网格系统：
    - 尤其适合红利ETF (510880)、沪深300ETF (510300) 等低估值高波动的震荡标的
    - 将总本金切分为 6 ~ 8 份网格（每份约 2,000 ~ 3,000 元）
    - 网格步长（间距）通常为 1.5% ~ 2.0%
    - 当价格下跌一个网格步长时：自动挂单买入一份
    - 当价格反弹一个网格步长时：自动挂单止盈卖出一份
    - 免印花税优势使得 ETF 网格交易的摩擦成本极低，能在震荡市源源不断产生现金流
    """
    def __init__(
        self,
        symbol: str = "510880",           # 默认标的：红利ETF (低估值高股息，非常适合网格)
        grid_step_pct: float = 0.015,     # 网格步长：1.5%
        grid_levels: int = 6,             # 网格层级数
        per_grid_amount: float = 2500.0,  # 每格投入金额：约 2,500 元
        base_center_price: Optional[float] = None
    ):
        super().__init__(name="Adaptive_ETF_Grid", symbols=[symbol])
        self.symbol = symbol
        self.grid_step_pct = grid_step_pct
        self.grid_levels = grid_levels
        self.per_grid_amount = per_grid_amount
        self.base_center_price = base_center_price
        self.last_grid_level: Optional[int] = None  # 记录当前所处的网格层级

    def generate_signals(
        self, 
        data_dict: Dict[str, pd.DataFrame], 
        account: Account,
        realtime_quotes: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Signal]:
        signals = []
        symbol = self.symbol

        # 获取最新价格
        if realtime_quotes and symbol in realtime_quotes:
            curr_price = realtime_quotes[symbol]["price"]
        elif symbol in data_dict and not data_dict[symbol].empty:
            curr_price = float(data_dict[symbol].iloc[-1]["close"])
        else:
            return signals

        # 确定基准中心价 (若未指定，则取近20日均价作为网格中心)
        if self.base_center_price is None:
            if symbol in data_dict and len(data_dict[symbol]) >= 20:
                self.base_center_price = float(data_dict[symbol]["close"].tail(20).mean())
                logger.info(f"[{symbol}] 网格基准中心价初始化为20日均价: ¥{self.base_center_price:.3f}")
            else:
                self.base_center_price = curr_price

        # 计算当前价格相对基准价的偏离格数
        # level = 0 代表中心价，-1 代表跌破1格，+1 代表上涨1格
        price_ratio = curr_price / self.base_center_price
        current_level = int(round((price_ratio - 1.0) / self.grid_step_pct))

        pos = account.positions.get(symbol)
        curr_qty = pos.total_qty if pos else 0
        avail_qty = pos.available_qty if pos else 0

        # 如果首次运行，初始化所处层级
        if self.last_grid_level is None:
            self.last_grid_level = current_level
            # 首次建仓底仓 (若当前无持仓且价格合理，买入首格)
            if curr_qty == 0 and account.cash >= self.per_grid_amount:
                buy_qty = int(self.per_grid_amount // (curr_price * LOT_SIZE)) * LOT_SIZE
                if buy_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="BUY",
                        price=curr_price,
                        qty=buy_qty,
                        strategy_name=self.name,
                        reason=f"网格系统建立初始底仓: 现价 ¥{curr_price:.3f}"
                    ))
            return signals

        # 1. 价格下穿网格线 (逢低买入加仓)
        if current_level < self.last_grid_level:
            # 价格下跌了至少一格
            levels_dropped = self.last_grid_level - current_level
            target_amount = self.per_grid_amount * min(levels_dropped, 2)
            
            if account.cash >= target_amount and current_level >= -self.grid_levels:
                buy_qty = int(target_amount // (curr_price * LOT_SIZE)) * LOT_SIZE
                if buy_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="BUY",
                        price=curr_price,
                        qty=buy_qty,
                        strategy_name=self.name,
                        reason=f"网格下轨触发买入: 现价 ¥{curr_price:.3f} 下跌至第 {current_level} 格"
                    ))
                    self.last_grid_level = current_level

        # 2. 价格上穿网格线 (逢高减仓止盈)
        elif current_level > self.last_grid_level:
            # 价格反弹了至少一格
            if avail_qty > 0 and current_level <= self.grid_levels:
                # 每次卖出一格的标准股数
                single_grid_qty = int(self.per_grid_amount // (curr_price * LOT_SIZE)) * LOT_SIZE
                sell_qty = min(avail_qty, single_grid_qty)
                if sell_qty >= LOT_SIZE:
                    signals.append(Signal(
                        symbol=symbol,
                        action="SELL",
                        price=curr_price,
                        qty=sell_qty,
                        strategy_name=self.name,
                        reason=f"网格上轨触发卖出止盈: 现价 ¥{curr_price:.3f} 反弹至第 {current_level} 格"
                    ))
                    self.last_grid_level = current_level

        return signals
