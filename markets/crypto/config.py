"""
加密货币市场规则配置 (币安 Binance)
Crypto Market Configurations & Rules (Binance Spot)
"""

import os
from pathlib import Path
from config import BASE_DIR

MARKET_NAME = "crypto"
CURRENCY = "USDT"
INITIAL_CASH = 5000.0           # 默认初始资金 5000 USDT

DATA_DIR = BASE_DIR / "data" / "crypto"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "quant_trading.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ----------------- 币安 API 凭据与网络 -----------------
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
BINANCE_PROXY = os.getenv("BINANCE_PROXY", "").strip() or None
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com").rstrip("/")

# ----------------- 交易规则与税费 -----------------
MAKER_FEE_RATE = 0.001          # 挂单手续费率 (0.1%)
TAKER_FEE_RATE = 0.001          # 吃单手续费率 (0.1%)
DEFAULT_SLIPPAGE = 0.0005       # 模拟成交滑点 (0.05%)
T_PLUS_1 = False                # 7x24 T+0 交易制度：买入立即可以卖出
LOT_SIZE = None                 # 支持小数位碎股报单

# ----------------- 默认监控与交易标的池 (主流现货交易对) -----------------
DEFAULT_SYMBOLS = {
    "BTCUSDT": {
        "name": "比特币", 
        "base": "BTC", 
        "quote": "USDT", 
        "min_qty": 0.00001, 
        "qty_precision": 5, 
        "price_precision": 2
    },
    "ETHUSDT": {
        "name": "以太坊", 
        "base": "ETH", 
        "quote": "USDT", 
        "min_qty": 0.0001, 
        "qty_precision": 4, 
        "price_precision": 2
    },
    "SOLUSDT": {
        "name": "SOL", 
        "base": "SOL", 
        "quote": "USDT", 
        "min_qty": 0.01, 
        "qty_precision": 2, 
        "price_precision": 2
    },
    "BNBUSDT": {
        "name": "BNB", 
        "base": "BNB", 
        "quote": "USDT", 
        "min_qty": 0.001, 
        "qty_precision": 3, 
        "price_precision": 2
    },
}

def normalize_symbol(symbol: str) -> str:
    """标准化标的名称，例如将 'BTC/USDT' 或 'btc_usdt' 转化为 'BTCUSDT'"""
    s = str(symbol).strip().upper()
    return s.replace("/", "").replace("_", "").replace("-", "")

def get_symbol_precision(symbol: str) -> int:
    norm = normalize_symbol(symbol)
    if norm in DEFAULT_SYMBOLS:
        return DEFAULT_SYMBOLS[norm]["qty_precision"]
    return 4
