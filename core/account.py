"""
模拟账户与持仓管理模块
Simulated Account & Position Tracker with Multi-Market Rules (T+0/T+1, CNY/USDT)
"""

import datetime
from typing import Dict, List, Optional, Any
from config import INITIAL_CASH
from core.storage import DBManager
from utils.logger import get_logger

logger = get_logger("Account")

class Position:
    def __init__(
        self,
        symbol: str,
        symbol_name: str,
        total_qty: float = 0.0,
        available_qty: float = 0.0,
        cost_price: float = 0.0,
        current_price: float = 0.0
    ):
        self.symbol = symbol
        self.symbol_name = symbol_name
        self.total_qty = float(total_qty)              # 总持仓数 (支持整手或加密货币浮点数)
        self.available_qty = float(available_qty)      # 可用卖出数
        self.cost_price = float(cost_price)            # 持仓成本价
        self.current_price = float(current_price)      # 当前最新市价

    @property
    def market_value(self) -> float:
        """当前最新市值"""
        return self.total_qty * self.current_price

    @property
    def floating_pnl(self) -> float:
        """浮动盈亏额"""
        return (self.current_price - self.cost_price) * self.total_qty

    @property
    def floating_pnl_ratio(self) -> float:
        """浮动盈亏率"""
        if self.cost_price <= 0:
            return 0.0
        return (self.current_price - self.cost_price) / self.cost_price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "symbol_name": self.symbol_name,
            "total_qty": round(self.total_qty, 6) if not self.total_qty.is_integer() else int(self.total_qty),
            "available_qty": round(self.available_qty, 6) if not self.available_qty.is_integer() else int(self.available_qty),
            "cost_price": round(self.cost_price, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 2),
            "floating_pnl": round(self.floating_pnl, 2),
            "pnl_ratio": f"{self.floating_pnl_ratio * 100:.2f}%"
        }

class Account:
    def __init__(
        self,
        db: DBManager,
        initial_cash: float = INITIAL_CASH,
        currency: str = "CNY"
    ):
        self.db = db
        self.currency = currency
        self.cash: float = initial_cash
        self.frozen_cash: float = 0.0
        self.initial_cash: float = initial_cash
        self.realized_pnl: float = 0.0
        self.positions: Dict[str, Position] = {}
        self.load()

    def load(self):
        """从 SQLite 数据库加载账户及持仓状态"""
        acc_info = self.db.load_account()
        if acc_info:
            self.cash = float(acc_info.get("cash", self.initial_cash))
            self.frozen_cash = float(acc_info.get("frozen_cash", 0.0))
            self.initial_cash = float(acc_info.get("initial_cash", self.initial_cash))
            self.realized_pnl = float(acc_info.get("realized_pnl", 0.0))

        pos_dict = self.db.load_positions()
        self.positions.clear()
        for sym, p in pos_dict.items():
            self.positions[sym] = Position(
                symbol=sym,
                symbol_name=p.get("symbol_name", ""),
                total_qty=float(p.get("total_qty", 0.0)),
                available_qty=float(p.get("available_qty", 0.0)),
                cost_price=float(p.get("cost_price", 0.0)),
                current_price=float(p.get("current_price", 0.0))
            )

    def save(self):
        """将当前账户状态及持仓同步保存到数据库"""
        self.db.update_account(
            cash=self.cash,
            frozen_cash=self.frozen_cash,
            total_equity=self.total_equity,
            realized_pnl=self.realized_pnl
        )
        for sym, pos in self.positions.items():
            self.db.save_position(pos.to_dict())

    @property
    def market_value(self) -> float:
        """持仓总市值"""
        return sum(pos.market_value for pos in self.positions.values())

    @property
    def total_equity(self) -> float:
        """账户动态总资产 = 可用现金 + 冻结资金 + 持仓市值"""
        return self.cash + self.frozen_cash + self.market_value

    @property
    def total_pnl(self) -> float:
        """总盈亏额 = 动态总资产 - 初始资金"""
        return self.total_equity - self.initial_cash

    @property
    def total_return_ratio(self) -> float:
        """累计总收益率"""
        if self.initial_cash <= 0:
            return 0.0
        return self.total_pnl / self.initial_cash

    def update_quotes(self, quotes: Dict[str, Dict[str, Any]]):
        """根据最新市场行情更新持仓价格与市值"""
        for sym, pos in self.positions.items():
            if sym in quotes:
                pos.current_price = quotes[sym]["price"]
                if not pos.symbol_name and quotes[sym].get("name"):
                    pos.symbol_name = quotes[sym]["name"]
        self.save()

    def settle_daily_t_plus_1(self):
        """日终结算：T+1 规则生效，当天买入的冻结可用股解冻，全部转为可卖"""
        for sym, pos in self.positions.items():
            if pos.available_qty < pos.total_qty:
                logger.info(f"[{sym}] T+1日终结算: 可卖份额由 {pos.available_qty} 更新为 {pos.total_qty}")
                pos.available_qty = pos.total_qty
        self.save()

    def print_summary(self):
        """打印格式化账户资产报告"""
        curr = self.currency
        print("\n" + "=" * 60)
        print(f"          【 模拟量化交易账户总览 ({curr}) 】")
        print("=" * 60)
        print(f" 初始本金:   {self.initial_cash:>12,.2f} {curr}    更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f" 可用现金:   {self.cash:>12,.2f} {curr}    持仓市值: {self.market_value:>12,.2f} {curr}")
        print(f" 动态总资产: {self.total_equity:>12,.2f} {curr}    已实现盈亏: {self.realized_pnl:>10,.2f} {curr}")
        
        pnl_color = "+" if self.total_pnl >= 0 else ""
        print(f" 累计总盈亏: {pnl_color}{self.total_pnl:>11,.2f} {curr}    累计收益率: {pnl_color}{self.total_return_ratio * 100:.2f}%")
        print("-" * 60)
        if not self.positions:
            print(" 当前空仓，暂无持仓标的。")
        else:
            print(f" {'代码':<9} {'名称':<8} {'持仓数':>9} {'可用数':>9} {'成本价':>8} {'现价':>8} {'盈亏率':>8}")
            for sym, pos in self.positions.items():
                pnl_str = f"{pos.floating_pnl_ratio * 100:+.2f}%"
                t_qty_str = f"{pos.total_qty:.4f}".rstrip("0").rstrip(".") if not pos.total_qty.is_integer() else str(int(pos.total_qty))
                a_qty_str = f"{pos.available_qty:.4f}".rstrip("0").rstrip(".") if not pos.available_qty.is_integer() else str(int(pos.available_qty))
                print(f" {pos.symbol:<9} {pos.symbol_name[:6]:<8} {t_qty_str:>9} {a_qty_str:>9} "
                      f"{pos.cost_price:>8.3f} {pos.current_price:>8.3f} {pnl_str:>8}")
        print("=" * 60 + "\n")
