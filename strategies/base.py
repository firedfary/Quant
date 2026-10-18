"""
策略基类与信号规范
Base Strategy & Trading Signal Specification
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import pandas as pd
from core.account import Account

@dataclass
class Signal:
    symbol: str
    action: str           # "BUY", "SELL", "HOLD"
    price: float          # 触发时的参考市价
    qty: float            # 建议交易数量 (A股为100整手，加密货币可为浮点数)
    strategy_name: str    # 策略名称
    reason: str           # 信号触发原因说明

class BaseStrategy(ABC):
    def __init__(self, name: str, symbols: List[str]):
        self.name = name
        self.symbols = symbols

    @abstractmethod
    def generate_signals(
        self, 
        data_dict: Dict[str, pd.DataFrame], 
        account: Account,
        realtime_quotes: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Signal]:
        """
        根据历史 K 线数据与实时行情，生成交易买卖信号
        :param data_dict: 历史K线字典 {symbol: DataFrame}
        :param account: 当前模拟账户对象 (用于获取可用现金及持仓)
        :param realtime_quotes: 当前最新实时行情 (用于实时盘中触发)
        :return: 信号列表
        """
        pass
