"""
A 股与场内 ETF 交易市场规则配置
A-Share / ETF Market Configurations & Rules
"""

from pathlib import Path
from config import BASE_DIR

MARKET_NAME = "ashare"
CURRENCY = "CNY"
INITIAL_CASH = 20000.0

DATA_DIR = BASE_DIR / "data" / "ashare"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "quant_trading.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ----------------- 交易规则与税费 -----------------
COMMISSION_RATE = 0.00025       # 佣金率：万分之 2.5
MIN_COMMISSION_STOCK = 5.0      # 股票单笔最低 5 元
MIN_COMMISSION_ETF = 0.2        # ETF 券商免5元限制，最低 0.2 元

STAMP_TAX_STOCK = 0.0005        # 股票印花税：卖出单向收取千分之 0.5 (2023年8月后)
STAMP_TAX_ETF = 0.0             # ETF 印花税：免征 (0%)

TRANSFER_FEE_RATE = 0.00001     # 过户费：双向十万分之一 (0.001%)
DEFAULT_SLIPPAGE = 0.001        # 模拟成交滑点率 (0.1%)

LOT_SIZE = 100                  # 最小交易单位：必须是 100 股/份的整数倍
T_PLUS_1 = True                 # T+1 交易制度：当天买入次日可卖

# ----------------- 默认标的池 (优质场内宽基/行业ETF) -----------------
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
