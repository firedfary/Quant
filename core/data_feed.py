"""
行情数据管理中心路由与向后兼容层
"""
from core.base_data_feed import BaseDataFeed
from markets.ashare.data_feed import AshareDataFeed
from markets.crypto.data_feed import CryptoDataFeed

# 保持向后兼容性
DataFeed = AshareDataFeed

__all__ = ["BaseDataFeed", "AshareDataFeed", "CryptoDataFeed", "DataFeed"]
