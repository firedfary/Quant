"""
量化交易系统全局配置文件
Global Configuration for Quantitative Trading System
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ----------------- 资金与交易规则配置 -----------------
# 初始模拟资金 (人民币)
INITIAL_CASH = 20000.0

# 交易成本设定 (模拟真实 A股/场内ETF 规则)
COMMISSION_RATE = 0.00025       # 佣金率：万分之 2.5
MIN_COMMISSION_STOCK = 5.0      # 股票单笔最低佣金 5 元
MIN_COMMISSION_ETF = 0.2        # ETF 券商普遍免 5 元限制，按实际或最低 0.2 元收取

STAMP_TAX_STOCK = 0.0005        # 股票印花税：卖出单向收取千分之 0.5 (2023年8月减半后)
STAMP_TAX_ETF = 0.0             # ETF 印花税：免征 (0%)

TRANSFER_FEE_RATE = 0.00001     # 过户费：双向收取十万分之一 (0.001%)
DEFAULT_SLIPPAGE = 0.001        # 模拟成交滑点率 (0.1%)

LOT_SIZE = 100                  # 最小交易单位 (1手 = 100股/份)
T_PLUS_1 = True                 # 是否启用 A 股 T+1 交易制度 (当天买入次日可卖)

# ----------------- 数据库与日志 -----------------
DB_PATH = DATA_DIR / "quant_trading.db"
LOG_FILE = LOG_DIR / "quant_trading.log"

# ----------------- 默认监控/交易标的池 (优质场内ETF) -----------------
# 2万元资金非常适合在低费率、无印花税的宽基与行业ETF中进行量化策略运作
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
    # 沪市ETF 51xxxx, 56xxxx, 58xxxx; 深市ETF 15xxxx
    if s.startswith(('51', '56', '58', '15')):
        return True
    return False
