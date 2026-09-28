"""
模拟账户与持仓管理模块
Simulated Account & Position Tracker with T+1 Rules
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
        total_qty: int = 0,
        available_qty: int = 0,
        cost_price: float = 0.0,
        current_price: float = 0.0
    ):
        self.symbol = symbol
        self.symbol_name = symbol_name
        self.total_qty = total_qty              # 总持仓股数
        self.available_qty = available_qty      # T+1 可用卖出股数
        self.cost_price = cost_price            # 持仓成本价
        self.current_price = current_price      # 当前最新市价

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
            "total_qty": self.total_qty,
            "available_qty": self.available_qty,
            "cost_price": round(self.cost_price, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 2),
            "floating_pnl": round(self.floating_pnl, 2),
            "pnl_ratio": f"{self.floating_pnl_ratio * 100:.2f}%"
        }

class Account:
    def __init__(self, db: DBManager):
        self.db = db
        self.cash: float = INITIAL_CASH
        self.frozen_cash: float = 0.0
        self.initial_cash: float = INITIAL_CASH
        self.realized_pnl: float = 0.0
        self.positions: Dict[str, Position] = {}
        self.load()

    def load(self):
        """从 SQLite 数据库加载账户及持仓状态"""
        acc_info = self.db.load_account()
        self.cash = float(acc_info.get("cash", INITIAL_CASH))
        self.frozen_cash = float(acc_info.get("frozen_cash", 0.0))
        self.initial_cash = float(acc_info.get("initial_cash", INITIAL_CASH))
        self.realized_pnl = float(acc_info.get("realized_pnl", 0.0))

        pos_dict = self.db.load_positions()
        self.positions.clear()
        for sym, p in pos_dict.items():
            self.positions[sym] = Position(
                symbol=sym,
                symbol_name=p.get("symbol_name", ""),
                total_qty=int(p.get("total_qty", 0)),
                available_qty=int(p.get("available_qty", 0)),
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
                logger.info(f"[{sym}] T+1日终结算: 可卖股数由 {pos.available_qty} 更新为 {pos.total_qty}")
                pos.available_qty = pos.total_qty
        self.save()

    def print_summary(self):
        """打印格式化账户资产报告"""
        print("\n" + "=" * 58)
        print("          【 20,000 元 模拟量化交易账户总览 】")
        print("=" * 58)
        print(f" 初始本金:   {self.initial_cash:>12,.2f} 元    更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f" 可用现金:   {self.cash:>12,.2f} 元    持仓市值: {self.market_value:>12,.2f} 元")
        print(f" 动态总资产: {self.total_equity:>12,.2f} 元    已实现盈亏: {self.realized_pnl:>10,.2f} 元")
        
        pnl_color = "+" if self.total_pnl >= 0 else ""
        print(f" 累计总盈亏: {pnl_color}{self.total_pnl:>11,.2f} 元    累计收益率: {pnl_color}{self.total_return_ratio * 100:.2f}%")
        print("-" * 58)
        if not self.positions:
            print(" 当前空仓，暂无持仓标的。")
        else:
            print(f" {'代码':<7} {'名称':<8} {'持仓数':>6} {'可用数':>6} {'成本价':>7} {'现价':>7} {'盈亏率':>8}")
            for sym, pos in self.positions.items():
                pnl_str = f"{pos.floating_pnl_ratio * 100:+.2f}%"
                print(f" {pos.symbol:<7} {pos.symbol_name[:4]:<8} {pos.total_qty:>6} {pos.available_qty:>6} "
                      f"{pos.cost_price:>7.3f} {pos.current_price:>7.3f} {pnl_str:>8}")
        print("=" * 58 + "\n")
