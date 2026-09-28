"""
风控管理模块
Risk Management Engine for Capital & Position Protection
"""

from typing import Dict, Tuple
from core.account import Account
from utils.logger import get_logger

logger = get_logger("RiskManager")

class RiskManager:
    def __init__(
        self, 
        max_pos_ratio: float = 0.60,      # 单个标的最大仓位占比 (如 60%)
        stop_loss_ratio: float = 0.08,    # 单个持仓硬止损线 (如 -8%)
        max_account_drawdown: float = 0.15 # 账户最大允许回撤 (如 15%)
    ):
        self.max_pos_ratio = max_pos_ratio
        self.stop_loss_ratio = stop_loss_ratio
        self.max_account_drawdown = max_account_drawdown

    def check_buy_order(self, account: Account, symbol: str, price: float, qty: int) -> Tuple[bool, str]:
        """
        下单前风控检查：
        1. 检查单标的持仓市值是否会突破上限
        2. 检查账户总回撤是否触及熔断
        """
        est_amount = price * qty
        total_equity = account.total_equity

        # 检查账户是否触及总回撤熔断
        drawdown = (account.initial_cash - total_equity) / account.initial_cash
        if drawdown >= self.max_account_drawdown:
            return False, f"账户触及回撤熔断线 ({drawdown*100:.1f}% >= {self.max_account_drawdown*100:.1f}%)，暂停新开仓！"

        # 检查单标的仓位上限
        current_pos_mv = account.positions[symbol].market_value if symbol in account.positions else 0.0
        new_pos_mv = current_pos_mv + est_amount
        pos_ratio = new_pos_mv / total_equity

        if pos_ratio > self.max_pos_ratio:
            return False, f"单标的仓位超限：预计占比 {pos_ratio*100:.1f}% > 最大允许 {self.max_pos_ratio*100:.1f}%"

        return True, "风控通过"

    def check_stop_loss_triggers(self, account: Account) -> Dict[str, str]:
        """
        盘中巡检持仓是否触及个股硬止损线
        :return: 触发止损的标的字典 {symbol: 止损原因}
        """
        triggers = {}
        for sym, pos in account.positions.items():
            if pos.cost_price > 0:
                pnl_ratio = pos.floating_pnl_ratio
                if pnl_ratio <= -self.stop_loss_ratio:
                    triggers[sym] = f"浮亏已达 {pnl_ratio*100:.2f}% (触及止损线 -{self.stop_loss_ratio*100:.1f}%)"
        return triggers
