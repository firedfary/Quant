"""
外汇小游戏市场规则配置 (FX 简单! / FX PLAYROOM)
FX Toy Market Configurations & Rules
"""

import os
from pathlib import Path
from config import BASE_DIR

MARKET_NAME = "fx_toy"
CURRENCY = "USD"
INITIAL_CASH = 10000.0          # 游戏初始虚拟本金 $10,000

DATA_DIR = BASE_DIR / "data" / "fx_toy"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "quant_trading.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ----------------- 游戏直链与调试参数 -----------------
GAME_URL = "https://www.bilibilitoy.com/toy/fx-simple/37279699568640-v24785/index.html"
DEBUG_PORT = 9222
WS_PORT = 8765

# ----------------- 交易规则与费用 -----------------
DEFAULT_SLIPPAGE = 0.0001       # 模拟成交滑点
T_PLUS_1 = False                # 7x24 T+0 外汇双向交易
DEFAULT_LEVERAGE = 20           # 默认推荐杠杆倍数 (支持 1 ~ 100)
MIN_MARGIN = 10.0               # 最低单笔开仓保证金 ($10)
MAKER_FEE_RATE = 0.0001         # 手续费参考率

# ----------------- 游戏支持的 7 大主流货币对 -----------------
DEFAULT_SYMBOLS = {
    "EUR/USD": {"name": "欧元 / 美元", "base": "EUR", "quote": "USD", "digits": 5},
    "GBP/USD": {"name": "英镑 / 美元", "base": "GBP", "quote": "USD", "digits": 5},
    "USD/JPY": {"name": "美元 / 日元", "base": "USD", "quote": "JPY", "digits": 3},
    "USD/CHF": {"name": "美元 / 瑞郎", "base": "USD", "quote": "CHF", "digits": 5},
    "EUR/CHF": {"name": "欧元 / 瑞郎", "base": "EUR", "quote": "CHF", "digits": 5},
    "AUD/USD": {"name": "澳元 / 美元", "base": "AUD", "quote": "USD", "digits": 5},
    "USD/CAD": {"name": "美元 / 加元", "base": "USD", "quote": "CAD", "digits": 5},
}

def normalize_symbol(symbol: str) -> str:
    """标准化标的符号，例如将 'EURUSD' 转为 'EUR/USD'"""
    s = str(symbol).strip().upper()
    if "/" in s:
        return s
    if len(s) == 6:
        return f"{s[:3]}/{s[3:]}"
    return s
