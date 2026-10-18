"""
行情数据管理中心抽象基类
Abstract Base Data Feed for Multi-Market Quantitative Trading
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import pandas as pd
from utils.logger import get_logger

logger = get_logger("BaseDataFeed")

class BaseDataFeed(ABC):
    """
    通用行情数据提供者抽象基类。
    约定实时行情和历史 K 线统一格式输出。
    """

    @abstractmethod
    def get_realtime_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        获取多个标的的毫秒/秒级最新行情快照
        :param symbols: 标的代码列表
        :return: 字典映射 {symbol: {"price": float, "name": str, "volume": float, ...}}
        """
        pass

    @abstractmethod
    def get_history_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: Optional[str] = None,
        timeframe: str = "1d"
    ) -> pd.DataFrame:
        """
        获取单标的历史 K 线序列并返回标准化 DataFrame
        :return: DataFrame 包含列 ['date', 'open', 'close', 'high', 'low', 'volume']，按时间升序排列
        """
        pass
