"""
外汇小游戏撮合经纪商实现 (FX 简单!)
Simulated Broker for FX Toy (Margin Trading, 1-100x Leverage, Long/Short)
"""

import uuid
import datetime
import asyncio
from typing import Dict, Optional, Tuple, Any
from core.base_broker import BaseBroker
from core.account import Account, Position
from core.storage import DBManager
from markets.fx_toy.config import (
    MAKER_FEE_RATE, DEFAULT_SLIPPAGE, DEFAULT_LEVERAGE,
    normalize_symbol, DEFAULT_SYMBOLS
)
from markets.fx_toy.edge_runner import EdgeRunner
from utils.logger import get_logger

logger = get_logger("FxToyBroker")

class FxToyBroker(BaseBroker):
    def __init__(
        self, 
        account: Account, 
        db: DBManager, 
        slippage: float = DEFAULT_SLIPPAGE,
        leverage: int = DEFAULT_LEVERAGE,
        runner: Optional[EdgeRunner] = None
    ):
        super().__init__(account, db, slippage)
        self.leverage = leverage
        self.runner = runner

    def calculate_fees(self, symbol: str, action: str, deal_amount: float) -> Tuple[float, float, float, float]:
        """
        外汇手续费计算: 佣金 = 名义本金 * 费率
        """
        commission = round(deal_amount * MAKER_FEE_RATE, 4)
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
        执行买入/做多指令
        """
        norm_sym = normalize_symbol(symbol)
        margin = float(qty)
        if margin < 10.0:
            logger.warning(f"开仓拒绝 [{norm_sym}]: 保证金不能低于 $10")
            return None

        # 实际成交价与名义金额
        deal_price = round(price * (1.0 + self.slippage), 5)
        notional = margin * self.leverage
        commission, _, _, total_fees = self.calculate_fees(norm_sym, "BUY", notional)
        total_cost = margin + total_fees

        if self.account.cash < total_cost:
            logger.warning(
                f"买入拒绝 [{norm_sym}]: 可用余额不足！所需 ${total_cost:.2f} (含手续费 ${total_fees:.2f})，可用仅 ${self.account.cash:.2f}"
            )
            return None

        # 若绑定了真实的 EdgeRunner，直接下发点击
        if self.runner:
            try:
                asyncio.run(self.runner.place_trade(side="long", margin=margin, leverage=self.leverage))
                logger.info(f"已同步触发 Edge 页面做多点击: {norm_sym} 保证金=${margin} 杠杆={self.leverage}x")
            except Exception as e:
                logger.warning(f"下发 Edge 浏览器点击异常 (仍计入本地模拟记账): {e}")

        # 扣减账户现金
        self.account.cash -= total_cost
        
        pos = self.account.positions.get(norm_sym)
        if pos:
            # 加仓
            new_total = pos.total_qty + margin
            pos.cost_price = round(((pos.cost_price * pos.total_qty) + (deal_price * margin)) / new_total, 5)
            pos.total_qty = new_total
            pos.available_qty = new_total
            pos.current_price = deal_price
        else:
            name = symbol_name or DEFAULT_SYMBOLS.get(norm_sym, {}).get("name", norm_sym)
            self.account.positions[norm_sym] = Position(
                symbol=norm_sym,
                symbol_name=name,
                total_qty=margin,
                available_qty=margin,
                cost_price=deal_price,
                current_price=deal_price
            )

        order_id = f"FX_BUY_{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        order_record = {
            "order_id": order_id,
            "symbol": norm_sym,
            "symbol_name": symbol_name or (pos.symbol_name if pos else norm_sym),
            "action": "BUY_LONG",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": margin,
            "deal_amount": notional,
            "commission": commission,
            "stamp_tax": 0.0,
            "transfer_fee": 0.0,
            "total_cost": total_cost,
            "strategy_name": strategy_name,
            "remark": remark or f"杠杆: {self.leverage}x",
            "created_at": now_str
        }

        self.db.record_order(order_record)
        self.account.save()
        logger.info(f"做多成交 [{norm_sym}]: 保证金=${margin:.2f}, 名义=${notional:.2f}, 成交价={deal_price}, 杠杆={self.leverage}x")
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
        执行卖出平仓指令
        """
        norm_sym = normalize_symbol(symbol)
        pos = self.account.positions.get(norm_sym)
        if not pos or pos.available_qty <= 0:
            logger.warning(f"卖出拒绝 [{norm_sym}]: 当前无多头持仓可平")
            return None

        close_margin = min(float(qty), pos.available_qty)
        deal_price = round(price * (1.0 - self.slippage), 5)
        
        # 盈亏计算: 价格变动百分比 * 名义金额
        pnl_pct = (deal_price - pos.cost_price) / pos.cost_price
        floating_pnl = round(close_margin * self.leverage * pnl_pct, 4)
        
        notional = close_margin * self.leverage
        commission, _, _, total_fees = self.calculate_fees(norm_sym, "SELL", notional)

        # 回收资金 = 保证金 + 盈亏 - 手续费
        recovered = close_margin + floating_pnl - total_fees
        self.account.cash += recovered
        self.account.realized_pnl += floating_pnl

        # 触发 Edge 页面平仓
        if self.runner:
            try:
                asyncio.run(self.runner.close_first_position())
                logger.info(f"已同步触发 Edge 页面平仓点击: {norm_sym}")
            except Exception as e:
                logger.warning(f"触发 Edge 页面平仓失败: {e}")

        saved_name = pos.symbol_name
        pos.total_qty -= close_margin
        pos.available_qty -= close_margin
        if pos.total_qty <= 0.001:
            del self.account.positions[norm_sym]

        order_id = f"FX_SELL_{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        order_record = {
            "order_id": order_id,
            "symbol": norm_sym,
            "symbol_name": saved_name,
            "action": "SELL_CLOSE",
            "status": "FILLED",
            "deal_price": deal_price,
            "qty": close_margin,
            "deal_amount": notional,
            "commission": commission,
            "stamp_tax": 0.0,
            "transfer_fee": 0.0,
            "total_cost": total_fees,
            "strategy_name": strategy_name,
            "remark": f"平仓盈亏: ${floating_pnl:+.2f}",
            "created_at": now_str
        }

        self.db.record_order(order_record)
        self.account.save()
        logger.info(f"平仓成交 [{norm_sym}]: 回收资金=${recovered:.2f}, 盈亏=${floating_pnl:+.2f}")
        return order_record
