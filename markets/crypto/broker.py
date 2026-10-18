"""
加密货币撮合经纪商实现 (币安现货规则)
Simulated Broker for Cryptocurrency (T+0, Fractional Sizing, Maker/Taker Fees)
"""

import uuid
import datetime
from typing import Dict, Optional, Tuple, Any
from core.base_broker import BaseBroker
from core.account import Account, Position
from core.storage import DBManager
from markets.crypto.config import (
    TAKER_FEE_RATE, DEFAULT_SLIPPAGE, normalize_symbol,
    get_symbol_precision, DEFAULT_SYMBOLS
)
from utils.logger import get_logger

logger = get_logger("CryptoBroker")

class CryptoBroker(BaseBroker):
    def __init__(self, account: Account, db: DBManager, slippage: float = DEFAULT_SLIPPAGE):
        super().__init__(account, db, slippage)

    def calculate_fees(self, symbol: str, action: str, deal_amount: float) -> Tuple[float, float, float, float]:
        """
        计算加密货币现货手续费: (佣金, 0, 0, 总手续费)
        币安现货默认单边收取 0.1% (Taker)
        """
        commission = deal_amount * TAKER_FEE_RATE
        return commission, 0.0, 0.0, commission

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
        执行加密货币买入委托 (T+0 制度，买入立即进入可用持仓)
        """
        norm_sym = normalize_symbol(symbol)
        precision = get_symbol_precision(norm_sym)
        valid_qty = round(float(qty), precision)

        if valid_qty <= 0:
            logger.warning(f"买入拒绝 [{norm_sym}]: 数量必须大于 0，当前有效申报: {valid_qty}")
            return None

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 + self.slippage), 4)
        deal_amount = round(deal_price * valid_qty, 4)

        commission, _, _, total_fees = self.calculate_fees(norm_sym, "BUY", deal_amount)
        total_cost = deal_amount + total_fees

        # 校验现金是否充足
        if self.account.cash < total_cost:
            logger.warning(
                f"买入拒绝 [{norm_sym}]: USDT资金不足！所需 {total_cost:,.2f} USDT (含手续费 {total_fees:.4f} USDT)，可用现金仅 {self.account.cash:,.2f} USDT"
            )
            return None

        # 扣减现金
        self.account.cash -= total_cost

        if not symbol_name and norm_sym in DEFAULT_SYMBOLS:
            symbol_name = DEFAULT_SYMBOLS[norm_sym]["name"]

        # 更新或新增持仓 (T+0 即时可用)
        pos = self.account.positions.get(norm_sym)
        if pos is None:
            pos = self.account.positions[norm_sym] = Position(
                symbol=norm_sym,
                symbol_name=symbol_name,
                total_qty=valid_qty,
                available_qty=valid_qty,  # T+0 立即可以卖出
                cost_price=deal_price,
                current_price=price
            )
        else:
            old_qty = pos.total_qty
            old_cost_amt = old_qty * pos.cost_price
            new_qty = round(old_qty + valid_qty, precision)
            new_cost_price = (old_cost_amt + deal_amount + total_fees) / new_qty
            
            pos.total_qty = new_qty
            pos.available_qty = round(pos.available_qty + valid_qty, precision)
            pos.cost_price = new_cost_price
            pos.current_price = price

        order_id = str(uuid.uuid4())[:8]
        order_record = {
            "order_id": order_id,
            "symbol": norm_sym,
            "symbol_name": symbol_name or pos.symbol_name,
            "action": "BUY",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": valid_qty,
            "deal_amount": deal_amount,
            "commission": commission,
            "stamp_tax": 0.0,
            "transfer_fee": 0.0,
            "total_cost": total_cost,
            "strategy_name": strategy_name,
            "remark": remark,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.account.save()
        self.db.record_order(order_record)

        logger.info(
            f"✔ [币安买入成交] {norm_sym} ({symbol_name}) | 成交价: {deal_price:.4f} USDT | 数量: {valid_qty} | "
            f"成交额: {deal_amount:,.2f} USDT | 手续费: {total_fees:.4f} USDT | 剩余现金: {self.account.cash:,.2f} USDT"
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
        执行加密货币卖出委托 (T+0)
        """
        norm_sym = normalize_symbol(symbol)
        pos = self.account.positions.get(norm_sym)
        if not pos:
            logger.warning(f"卖出拒绝 [{norm_sym}]: 账户当前未持有该币种！")
            return None

        precision = get_symbol_precision(norm_sym)
        valid_qty = round(float(qty), precision)
        if valid_qty <= 0:
            logger.warning(f"卖出拒绝 [{norm_sym}]: 数量必须大于 0，当前有效申报: {valid_qty}")
            return None

        # 检查可用持仓数量 (预留极微小浮点误差 1e-7)
        if pos.available_qty + 1e-7 < valid_qty:
            logger.warning(
                f"卖出拒绝 [{norm_sym}]: 可用数量不足！当前可用 {pos.available_qty}，申报: {valid_qty}"
            )
            return None

        # 避免浮点微小误差导致剩余微量负数
        valid_qty = min(valid_qty, pos.available_qty)

        # 考虑滑点后的实际成交价
        deal_price = round(price * (1.0 - self.slippage), 4)
        deal_amount = round(deal_price * valid_qty, 4)

        commission, _, _, total_fees = self.calculate_fees(norm_sym, "SELL", deal_amount)
        net_proceeds = deal_amount - total_fees

        # 计算已实现盈亏
        cost_basis = pos.cost_price * valid_qty
        trade_pnl = net_proceeds - cost_basis

        # 更新持仓
        pos.total_qty = round(pos.total_qty - valid_qty, precision)
        pos.available_qty = round(pos.available_qty - valid_qty, precision)
        pos.current_price = price

        self.account.cash += net_proceeds
        self.account.realized_pnl += trade_pnl

        # 清仓移除
        if pos.total_qty <= 1e-7:
            del self.account.positions[norm_sym]

        order_id = str(uuid.uuid4())[:8]
        order_record = {
            "order_id": order_id,
            "symbol": norm_sym,
            "symbol_name": symbol_name or pos.symbol_name,
            "action": "SELL",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": valid_qty,
            "deal_amount": deal_amount,
            "commission": commission,
            "stamp_tax": 0.0,
            "transfer_fee": 0.0,
            "total_cost": total_fees,
            "strategy_name": strategy_name,
            "remark": remark,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.account.save()
        self.db.record_order(order_record)

        pnl_symbol = "+" if trade_pnl >= 0 else ""
        logger.info(
            f"✔ [币安卖出成交] {norm_sym} ({pos.symbol_name}) | 成交价: {deal_price:.4f} USDT | 数量: {valid_qty} | "
            f"到手现金: {net_proceeds:,.2f} USDT | 本笔盈亏: {pnl_symbol}{trade_pnl:,.2f} USDT | 剩余现金: {self.account.cash:,.2f} USDT"
        )
        return order_record
