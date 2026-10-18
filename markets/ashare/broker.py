"""
A 股撮合经纪商实现
Simulated Broker for A-Shares & ETFs (T+1, Lot Size 100, Taxes & Stamp Duty)
"""

import uuid
import datetime
from typing import Dict, Optional, Tuple, Any
from core.base_broker import BaseBroker
from core.account import Account, Position
from core.storage import DBManager
from markets.ashare.config import (
    COMMISSION_RATE, MIN_COMMISSION_STOCK, MIN_COMMISSION_ETF,
    STAMP_TAX_STOCK, STAMP_TAX_ETF, TRANSFER_FEE_RATE,
    DEFAULT_SLIPPAGE, LOT_SIZE, T_PLUS_1, is_etf
)
from utils.logger import get_logger

logger = get_logger("AshareBroker")

class AshareBroker(BaseBroker):
    def __init__(self, account: Account, db: DBManager, slippage: float = DEFAULT_SLIPPAGE):
        super().__init__(account, db, slippage)

    def calculate_fees(self, symbol: str, action: str, deal_amount: float) -> Tuple[float, float, float, float]:
        """
        计算 A 股交易税费: (佣金, 印花税, 过户费, 总税费)
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
        qty: float, 
        symbol_name: str = "", 
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行买入模拟委托
        :param qty: 买入股数 (必须是 LOT_SIZE=100 的整数倍)
        """
        int_qty = int(qty)
        if int_qty <= 0 or int_qty % LOT_SIZE != 0:
            logger.warning(f"买入拒绝 [{symbol}]: A股申报数量必须为 {LOT_SIZE} 的整数倍，当前申报: {qty}")
            return None

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 + self.slippage), 4)
        deal_amount = round(deal_price * int_qty, 2)

        commission, stamp_tax, transfer_fee, total_fees = self.calculate_fees(symbol, "BUY", deal_amount)
        total_cost = deal_amount + total_fees

        # 校验现金是否充足
        if self.account.cash < total_cost:
            logger.warning(
                f"买入拒绝 [{symbol}]: 资金不足！所需 ¥{total_cost:,.2f} (含税费¥{total_fees:.2f})，可用现金仅 ¥{self.account.cash:,.2f}"
            )
            return None

        # 扣减现金
        self.account.cash -= total_cost

        # 更新或新增持仓
        pos = self.account.positions.get(symbol)
        if pos is None:
            # 新建持仓: A 股 T+1 规则下，当天买入的股票 available_qty 为 0，下一交易日结算后才可卖
            avail = 0.0 if T_PLUS_1 else float(int_qty)
            pos = self.account.positions[symbol] = Position(
                symbol=symbol,
                symbol_name=symbol_name,
                total_qty=float(int_qty),
                available_qty=avail,
                cost_price=deal_price,
                current_price=price
            )
        else:
            old_qty = pos.total_qty
            old_cost_amt = old_qty * pos.cost_price
            new_qty = old_qty + int_qty
            new_cost_price = (old_cost_amt + deal_amount + total_fees) / new_qty
            
            pos.total_qty = new_qty
            pos.cost_price = new_cost_price
            pos.current_price = price
            if not T_PLUS_1:
                pos.available_qty += float(int_qty)

        order_id = str(uuid.uuid4())[:8]
        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "symbol_name": symbol_name or (pos.symbol_name if pos else ""),
            "action": "BUY",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": int_qty,
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
            f"✔ [A股买入成交] {symbol} {symbol_name} | 成交价: ¥{deal_price:.3f} | 数量: {int_qty}股 | "
            f"成交额: ¥{deal_amount:,.2f} | 手续费: ¥{total_fees:.2f} | 剩余现金: ¥{self.account.cash:,.2f}"
        )
        return order_record

    def sell(
        self, 
        symbol: str, 
        price: float, 
        qty: float, 
        symbol_name: str = "", 
        strategy_name: str = "Manual",
        remark: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        执行卖出模拟委托
        :param qty: 卖出股数 (必须是 LOT_SIZE=100 的整数倍)
        """
        pos = self.account.positions.get(symbol)
        if not pos:
            logger.warning(f"卖出拒绝 [{symbol}]: 账户当前未持有该标的！")
            return None

        int_qty = int(qty)
        if int_qty <= 0 or int_qty % LOT_SIZE != 0:
            logger.warning(f"卖出拒绝 [{symbol}]: A股申报数量必须为 {LOT_SIZE} 的整数倍，当前申报: {qty}")
            return None

        # 检查 T+1 可用持仓股数
        if pos.available_qty < int_qty:
            logger.warning(
                f"卖出拒绝 [{symbol}]: 可用股数不足！当前可用 {pos.available_qty}股 (总持仓 {pos.total_qty}股，T+1当日买入锁定中)，申报: {int_qty}股"
            )
            return None

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 - self.slippage), 4)
        deal_amount = round(deal_price * int_qty, 2)

        commission, stamp_tax, transfer_fee, total_fees = self.calculate_fees(symbol, "SELL", deal_amount)
        net_proceeds = deal_amount - total_fees

        # 计算该笔卖出的已实现盈亏
        cost_basis = pos.cost_price * int_qty
        trade_pnl = net_proceeds - cost_basis

        # 更新持仓数据
        pos.total_qty -= int_qty
        pos.available_qty -= int_qty
        pos.current_price = price

        # 增加可用现金与已实现盈亏
        self.account.cash += net_proceeds
        self.account.realized_pnl += trade_pnl

        # 若全部清仓，则从持仓字典移除
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
            "qty": int_qty,
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

        pnl_symbol = "+" if trade_pnl >= 0 else ""
        logger.info(
            f"✔ [A股卖出成交] {symbol} {symbol_name} | 成交价: ¥{deal_price:.3f} | 数量: {int_qty}股 | "
            f"到手现金: ¥{net_proceeds:,.2f} | 本笔盈亏: {pnl_symbol}¥{trade_pnl:,.2f} | 剩余现金: ¥{self.account.cash:,.2f}"
        )
        return order_record
