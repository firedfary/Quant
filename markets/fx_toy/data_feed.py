"""
外汇小游戏行情数据源实现 (FX 简单!)
Real-time Data Feed for FX Toy Simulation Game
"""

import asyncio
import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from core.base_data_feed import BaseDataFeed
from markets.fx_toy.config import (
    DEFAULT_SYMBOLS, normalize_symbol
)
from markets.fx_toy.edge_runner import EdgeRunner
from utils.logger import get_logger

logger = get_logger("FxToyDataFeed")

class FxToyDataFeed(BaseDataFeed):
    def __init__(self, runner: Optional[EdgeRunner] = None):
        self.runner = runner or EdgeRunner()
        self.tick_cache: Dict[str, Dict[str, Any]] = {}
        self.bar_cache: Dict[str, List[Dict[str, Any]]] = {}
        try:
            self.runner.launch_browser()
        except Exception as e:
            logger.warning(f"未能自动拉起 Edge 浏览器: {e}")

    def get_realtime_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        从正在运行的 Edge 游戏页面获取毫秒级最新行情快照
        """
        quotes = {}
        try:
            # 异步抓取最新状态
            state = asyncio.run(self.runner.get_state())
            current_pair = normalize_symbol(state.get("pair", "EUR/USD"))
            price = state.get("price", 1.0)

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for sym in symbols:
                norm_sym = normalize_symbol(sym)
                if norm_sym == current_pair and price > 0:
                    quotes[norm_sym] = {
                        "symbol": norm_sym,
                        "name": DEFAULT_SYMBOLS.get(norm_sym, {}).get("name", norm_sym),
                        "price": price,
                        "open": price,
                        "high": price,
                        "low": price,
                        "volume": 1000.0,
                        "time": now_str
                    }
                    self.tick_cache[norm_sym] = quotes[norm_sym]
                elif norm_sym in self.tick_cache:
                    quotes[norm_sym] = self.tick_cache[norm_sym]
                else:
                    # 回退到配置初始价格
                    init_p = DEFAULT_SYMBOLS.get(norm_sym, {}).get("digits", 5)
                    quotes[norm_sym] = {
                        "symbol": norm_sym,
                        "name": DEFAULT_SYMBOLS.get(norm_sym, {}).get("name", norm_sym),
                        "price": 1.0,
                        "volume": 0.0,
                        "time": now_str
                    }
        except Exception as e:
            logger.warning(f"获取实时行情异常，尝试复用缓存: {e}")
            quotes = self.tick_cache.copy()

        return quotes

    def get_history_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: Optional[str] = None,
        timeframe: str = "1d"
    ) -> pd.DataFrame:
        """
        获取历史 K 线数据，支持动态回测与技术指标初始化
        """
        norm_sym = normalize_symbol(symbol)
        now = datetime.datetime.now()
        dates = pd.date_range(end=now, periods=100, freq='h' if timeframe in ('1h', '60m') else 'D')
        
        # 初始基准价
        base_price = 1.0850 if "EUR" in norm_sym else 145.0
        # 随机游走生成连续 K 线
        returns = np.random.normal(0.0001, 0.003, size=len(dates))
        close_prices = base_price * np.exp(np.cumsum(returns))
        
        data = []
        for i, (dt, close) in enumerate(zip(dates, close_prices)):
            high = close * (1 + abs(np.random.normal(0, 0.002)))
            low = close * (1 - abs(np.random.normal(0, 0.002)))
            open_p = close * (1 + np.random.normal(0, 0.001))
            data.append({
                "date": dt.strftime("%Y-%m-%d %H:%M:%S" if timeframe != "1d" else "%Y-%m-%d"),
                "open": round(open_p, 5),
                "high": round(high, 5),
                "low": round(low, 5),
                "close": round(close, 5),
                "volume": int(np.random.uniform(5000, 20000))
            })

        df = pd.DataFrame(data)
        return df
