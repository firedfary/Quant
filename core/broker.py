"""
模拟撮合经纪商引擎
Simulated Broker with Real-Market Execution Rules (T+1, Lot Size, Fees, Slippage)
"""

import uuid
import datetime
from typing import Dict, Optional, Tuple, Any
from config import (
    COMMISSION_RATE, MIN_COMMISSION_STOCK, MIN_COMMISSION_ETF,
    STAMP_TAX_STOCK, STAMP_TAX_ETF, TRANSFER_FEE_RATE,
    DEFAULT_SLIPPAGE, LOT_SIZE, T_PLUS_1, is_etf
)
from core.account import Account, Position
from core.storage import DBManager
from utils.logger import get_logger

logger = get_logger("Broker")

class SimulatedBroker:
    def __init__(self, account: Account, db: DBManager, slippage: float = DEFAULT_SLIPPAGE):
        self.account = account
        self.db = db
        self.slippage = slippage

    def calculate_fees(self, symbol: str, action: str, deal_amount: float) -> Tuple[float, float, float, float]:
        """
        计算交易税费: (佣金, 印花税, 过户费, 总税费)
        """
        etf_flag = is_etf(symbol)
        
        # 1. 佣金 (双向收取)
        min_comm = MIN_COMMISSION_ETF if etf_flag else MIN_COMMISSION_STOCK
        commission = max(deal_amount * COMMISSION_RATE, min_comm)

        # 2. 印花税 (仅卖出收取，ETF 免征)
        if action.upper() == "SELL":
            stamp_tax = deal_amount * (STAMP_TAX_ETF if etf_flag else STAMP_TAX_STOCK)
        else:
            stamp_tax = 0.0

        # 3. 过户费 (双向收取，十万分之一)
        transfer_fee = deal_amount * TRANSFER_FEE_RATE

        total_fees = commission + stamp_tax + transfer_fee
        return commission, stamp_tax, transfer_fee, total_fees

    def buy(
        self, 
        symbol: str, 
        price: float, 
        qty: int, 
        symbol_name: str = "", 
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行买入模拟委托
        :param symbol: 标的代码 (如 '510300')
        :param price: 委托基准价
        :param qty: 买入股数 (必须是 LOT_SIZE=100 的整数倍)
        """
        if qty <= 0 or qty % LOT_SIZE != 0:
            logger.warning(f"买入拒绝 [{symbol}]: 数量必须为 {LOT_SIZE} 的整数倍，当前申报: {qty}")
            return None

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 + self.slippage), 4)
        deal_amount = round(deal_price * qty, 2)

        commission, stamp_tax, transfer_fee, total_fees = self.calculate_fees(symbol, "BUY", deal_amount)
        total_cost = deal_amount + total_fees

        # 校验现金是否充足
        if self.account.cash < total_cost:
            logger.warning(
                f"买入拒绝 [{symbol}]: 资金不足！所需 ¥{total_cost:,.2f} (含手续费¥{total_fees:.2f})，可用现金仅 ¥{self.account.cash:,.2f}"
            )
            return None

        # 扣减现金
        self.account.cash -= total_cost

        # 更新或新增持仓
        pos = self.account.positions.get(symbol)
        if pos is None:
            # 新建持仓: A 股 T+1 规则下，当天买入的股票 available_qty 为 0，下一交易日结算后才可卖
            avail = 0 if T_PLUS_1 else qty
            pos = self.account.positions[symbol] = Position(
                symbol=symbol,
                symbol_name=symbol_name,
                total_qty=qty,
                available_qty=avail,
                cost_price=deal_price,
                current_price=price
            )
        else:
            # 加仓计算摊薄成本
            old_qty = pos.total_qty
            old_cost_amt = old_qty * pos.cost_price
            new_qty = old_qty + qty
            new_cost_price = (old_cost_amt + deal_amount + total_fees) / new_qty
            
            pos.total_qty = new_qty
            pos.cost_price = new_cost_price
            pos.current_price = price
            if not T_PLUS_1:
                pos.available_qty += qty
            # T+1 下当天加仓的 qty 不进 available_qty

        order_id = str(uuid.uuid4())[:8]
        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "symbol_name": symbol_name or (pos.symbol_name if pos else ""),
            "action": "BUY",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": qty,
            "deal_amount": deal_amount,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "transfer_fee": transfer_fee,
            "total_cost": total_cost,
            "strategy_name": strategy_name,
            "remark": remark,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.account.save()
        self.db.record_order(order_record)

        logger.info(
            f"✔ [买入成交] {symbol} {symbol_name} | 成交价: ¥{deal_price:.3f} | 数量: {qty}股 | "
            f"成交额: ¥{deal_amount:,.2f} | 手续费: ¥{total_fees:.2f} | 剩余现金: ¥{self.account.cash:,.2f}"
        )
        return order_record

    def sell(
        self, 
        symbol: str, 
        price: float, 
        qty: int, 
        symbol_name: str = "", 
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行卖出模拟委托 (遵循 T+1 可用持仓校验)
        """
        pos = self.account.positions.get(symbol)
        if not pos:
            logger.warning(f"卖出拒绝 [{symbol}]: 账户中无此标的持仓！")
            return None

        if qty <= 0:
            logger.warning(f"卖出拒绝 [{symbol}]: 卖出数量必须大于 0！")
            return None

        # T+1 可用数量校验
        if qty > pos.available_qty:
            logger.warning(
                f"卖出拒绝 [{symbol}]: T+1 可用卖出数量不足！申报: {qty} 股，当前可用: {pos.available_qty} 股 "
                f"(总持仓 {pos.total_qty} 股，部分为今日买入冻结)"
            )
            return None

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 - self.slippage), 4)
        deal_amount = round(deal_price * qty, 2)

        commission, stamp_tax, transfer_fee, total_fees = self.calculate_fees(symbol, "SELL", deal_amount)
        net_cash_received = deal_amount - total_fees

        # 扣减持仓与可用数量
        pos.total_qty -= qty
        pos.available_qty -= qty
        pos.current_price = price

        # 计算并累加已实现盈亏 (单笔净利)
        realized_trade_pnl = (deal_price - pos.cost_price) * qty - total_fees
        self.account.realized_pnl += realized_trade_pnl

        # 现金增加
        self.account.cash += net_cash_received

        # 若全部平仓则清理
        if pos.total_qty <= 0:
            del self.account.positions[symbol]

        order_id = str(uuid.uuid4())[:8]
        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "symbol_name": symbol_name or pos.symbol_name,
            "action": "SELL",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": qty,
            "deal_amount": deal_amount,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "transfer_fee": transfer_fee,
            "total_cost": total_fees,
            "strategy_name": strategy_name,
            "remark": remark,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.account.save()
        self.db.record_order(order_record)

        logger.info(
            f"✔ [卖出成交] {symbol} {symbol_name} | 成交价: ¥{deal_price:.3f} | 数量: {qty}股 | "
            f"到手现金: ¥{net_cash_received:,.2f} | 交易税费: ¥{total_fees:.2f} | 盈亏: ¥{realized_trade_pnl:+,.2f}"
        )
        return order_record
