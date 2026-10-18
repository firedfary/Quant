"""
跨市场自适应网格交易策略 (A股 ETF / 加密货币 跨市场通用)
Adaptive Multi-Market Grid Trading Strategy
"""

from typing import Dict, List, Optional, Any
import pandas as pd
from core.account import Account
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("GridTrading")

class GridTradingStrategy(BaseStrategy):
    """
    自适应动态等比网格套利算法：
    - 支持 A 股 ETF (如 510880, 510300) 100 整手下单
    - 支持 币安加密货币 (如 BTCUSDT, ETHUSDT) 高精度小数下单
    """
    def __init__(
        self,
        symbol: str = "510880",           # 标的代码
        grid_step_pct: float = 0.015,     # 网格步长比例 (如 1.5%)
        grid_levels: int = 6,             # 网格层级数
        per_grid_amount: float = 2500.0,  # 每格拟投入资金 (元 或 USDT)
        lot_size: Optional[int] = None,   # 整手约束 (A股设为100，币圈设为None)
        qty_precision: int = 4,           # 小数位精度 (仅当 lot_size 为 None 时生效)
        base_center_price: Optional[float] = None
    ):
        super().__init__(name="Adaptive_Grid_Trading", symbols=[symbol])
        self.symbol = symbol
        self.grid_step_pct = grid_step_pct
        self.grid_levels = grid_levels
        self.per_grid_amount = per_grid_amount
        self.lot_size = lot_size
        self.qty_precision = qty_precision
        self.base_center_price = base_center_price
        self.last_grid_level: Optional[int] = None

    def _calc_order_qty(self, price: float, target_amount: float) -> float:
        """根据当前市场精度约束计算合规下单量"""
        if price <= 0:
            return 0.0
        if self.lot_size and self.lot_size > 0:
            # 整手约束 (A股规则)
            qty = int(target_amount // (price * self.lot_size)) * self.lot_size
            return float(qty)
        else:
            # 浮点小数 (加密货币规则)
            return round(target_amount / price, self.qty_precision)

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

        # 确定基准中心价 (默认取最近 20 日均价)
        if self.base_center_price is None:
            if symbol in data_dict and len(data_dict[symbol]) >= 20:
                self.base_center_price = float(data_dict[symbol]["close"].tail(20).mean())
                logger.info(f"[{symbol}] 网格基准中心价初始化为20日均价: {self.base_center_price:.4f}")
            else:
                self.base_center_price = curr_price

        # 计算当前价格相对基准价的偏离格数
        price_ratio = curr_price / self.base_center_price
        current_level = int(round((price_ratio - 1.0) / self.grid_step_pct))

        pos = account.positions.get(symbol)
        curr_qty = pos.total_qty if pos else 0.0
        avail_qty = pos.available_qty if pos else 0.0

        # 如果首次运行，初始化所处层级
        if self.last_grid_level is None:
            self.last_grid_level = current_level
            # 首次建仓底仓 (若当前无持仓且价格合理，买入首格)
            if curr_qty <= 0 and account.cash >= self.per_grid_amount:
                buy_qty = self._calc_order_qty(curr_price, self.per_grid_amount)
                if buy_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="BUY",
                        price=curr_price,
                        qty=buy_qty,
                        strategy_name=self.name,
                        reason=f"网格初始化底仓，当前位于第 {current_level} 格"
                    ))
            return signals

        # 价格下行触发买入
        if current_level < self.last_grid_level:
            levels_dropped = self.last_grid_level - current_level
            if current_level >= -self.grid_levels:
                buy_amount = self.per_grid_amount * min(levels_dropped, 2)
                if account.cash >= buy_amount:
                    buy_qty = self._calc_order_qty(curr_price, buy_amount)
                    if buy_qty > 0:
                        signals.append(Signal(
                            symbol=symbol,
                            action="BUY",
                            price=curr_price,
                            qty=buy_qty,
                            strategy_name=self.name,
                            reason=f"价格下跌触及第 {current_level} 格 (跌破 {levels_dropped} 格)，分批加仓"
                        ))
                        self.last_grid_level = current_level

        # 价格上行触发卖出止盈
        elif current_level > self.last_grid_level:
            levels_risen = current_level - self.last_grid_level
            if avail_qty > 0:
                sell_target_amount = self.per_grid_amount * min(levels_risen, 2)
                calc_qty = self._calc_order_qty(curr_price, sell_target_amount)
                sell_qty = min(avail_qty, calc_qty)
                if sell_qty > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        action="SELL",
                        price=curr_price,
                        qty=sell_qty,
                        strategy_name=self.name,
                        reason=f"价格反弹触及第 {current_level} 格 (上涨 {levels_risen} 格)，网格收割止盈"
                    ))
                    self.last_grid_level = current_level

        return signals
