"""
撮合经纪商抽象基类
Abstract Base Broker for Multi-Market Quantitative Trading
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple, Any
from core.storage import DBManager
from utils.logger import get_logger

logger = get_logger("BaseBroker")

class BaseBroker(ABC):
    """
    通用撮合经纪商抽象类。
    隔离不同交易市场（如 A股 T+1与整手约束、虚拟币 7x24 T+0与高精度小数）的具体交易规则。
    """
    def __init__(self, account: Any, db: DBManager, slippage: float = 0.001):
        self.account = account
        self.db = db
        self.slippage = slippage

    @abstractmethod
    def calculate_fees(self, symbol: str, action: str, deal_amount: float) -> Tuple[float, float, float, float]:
        """
        计算交易手续费/税费
        :return: (佣金, 印花税/附加费, 过户费/网络费, 总税费)
        """
        pass

    @abstractmethod
    def buy(
        self,
        symbol: str,
        price: float,
        qty: float,
        symbol_name: str = "",
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行买入撮合
        :param symbol: 标的代码 (如 '510300' 或 'BTCUSDT')
        :param price: 委托市价基准
        :param qty: 委托数量 (A股为100的整数倍，币圈为浮点数)
        :return: 成交订单记录字典，若被拒绝则返回 None
        """
        pass

    @abstractmethod
    def sell(
        self,
        symbol: str,
        price: float,
        qty: float,
        symbol_name: str = "",
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行卖出撮合
        :param symbol: 标的代码
        :param price: 委托市价基准
        :param qty: 委托数量
        :return: 成交订单记录字典，若被拒绝则返回 None
        """
        pass
