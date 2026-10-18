"""
撮合经纪商路由与向后兼容层
"""
from core.base_broker import BaseBroker
from markets.ashare.broker import AshareBroker
from markets.crypto.broker import CryptoBroker

# 保持向后兼容性
SimulatedBroker = AshareBroker

__all__ = ["BaseBroker", "AshareBroker", "CryptoBroker", "SimulatedBroker"]
