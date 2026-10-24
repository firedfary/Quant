"""
量化交易系统全局核心配置与多市场路由中枢
Global Configuration & Multi-Market Router
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

DEFAULT_ENV_FILE = BASE_DIR / ".env"

def load_env(env_file: Optional[Path] = None, override: bool = False) -> Dict[str, str]:
    """
    加载 .env 配置文件中的环境变量
    """
    path = env_file or DEFAULT_ENV_FILE
    loaded = {}
    if not path.exists():
        return loaded

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = val
            loaded[key] = os.environ.get(key, val)
    return loaded

# 自动在模块载入时加载环境变量
load_env()

# ----------------- 默认回退配置 (兼容老版本直接引用) -----------------
INITIAL_CASH = 20000.0
COMMISSION_RATE = 0.00025
MIN_COMMISSION_STOCK = 5.0
MIN_COMMISSION_ETF = 0.2
STAMP_TAX_STOCK = 0.0005
STAMP_TAX_ETF = 0.0
TRANSFER_FEE_RATE = 0.00001
DEFAULT_SLIPPAGE = 0.001
LOT_SIZE = 100
T_PLUS_1 = True

DB_PATH = DATA_DIR / "quant_trading.db"
LOG_FILE = LOG_DIR / "quant_trading.log"

DEFAULT_SYMBOLS = {
    "510300": {"name": "沪深300ETF", "market": "SH", "type": "ETF"},
    "513100": {"name": "纳指ETF",    "market": "SH", "type": "ETF"},
    "518880": {"name": "黄金ETF",    "market": "SH", "type": "ETF"},
    "159915": {"name": "创业板ETF",  "market": "SZ", "type": "ETF"},
    "510880": {"name": "红利ETF",    "market": "SH", "type": "ETF"},
}

def is_etf(symbol: str) -> bool:
    """根据标的代码判断是否为 ETF 基金"""
    s = str(symbol).strip()
    if s in DEFAULT_SYMBOLS and DEFAULT_SYMBOLS[s]["type"] == "ETF":
        return True
    if s.startswith(('51', '56', '58', '15')):
        return True
    return False

def get_market_config(market_name: str = "ashare"):
    """
    根据市场名称获取对应市场的配置对象
    :param market_name: 'ashare', 'crypto', 或 'fx_toy'
    """
    market = str(market_name).lower().strip()
    if market in ("crypto", "binance", "coin"):
        from markets.crypto import config as crypto_cfg
        return crypto_cfg
    elif market in ("fx_toy", "fx", "toy", "fx-simple"):
        from markets.fx_toy import config as fx_cfg
        return fx_cfg
    else:
        from markets.ashare import config as ashare_cfg
        return ashare_cfg
