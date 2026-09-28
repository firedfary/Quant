"""
实盘模拟交易运行引擎
Live Paper Trading Engine (Real Market Quotes + SQLite Account + Risk Guard)
"""

import time
import datetime
from typing import Dict, List, Optional
import pandas as pd
from config import LOT_SIZE, DEFAULT_SYMBOLS
from core.data_feed import DataFeed
from core.account import Account
from core.broker import SimulatedBroker
from core.storage import DBManager
from core.risk_manager import RiskManager
from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger("PaperEngine")

class PaperTradingEngine:
    def __init__(
        self,
        strategy: BaseStrategy,
        db_path: Optional[str] = None
    ):
        self.strategy = strategy
        self.db = DBManager(db_path) if db_path else DBManager()
        self.account = Account(db=self.db)
        self.broker = SimulatedBroker(account=self.account, db=self.db)
        self.data_feed = DataFeed()
        self.risk_manager = RiskManager()

    def is_market_hours(self) -> bool:
        """检查当前是否处于 A 股/场内基金开盘交易时间"""
        now = datetime.datetime.now()
        # 周末不开盘 (0=周一, 6=周日)
        if now.weekday() >= 5:
            return False

        t = now.time()
        morning_open = datetime.time(9, 30) <= t <= datetime.time(11, 30)
        afternoon_open = datetime.time(13, 0) <= t <= datetime.time(15, 0)
        return morning_open or afternoon_open

    def run_step(self, force_execution: bool = True) -> List[Dict]:
        """
        执行一次实盘模拟巡检与信号撮合：
        1. 抓取最新毫秒级实时行情
        2. 更新持仓标的最新市值
        3. 巡检风控硬止损线
        4. 获取近期K线，送入策略生成信号
        5. 撮合成交并落盘数据库
        """
        logger.info(f"==> 执行实盘模拟交易巡检 [{self.strategy.name}]...")
        executed_orders = []

        # 确定需要监控的标的列表 (策略监控标的 + 账户现有持仓标的)
        active_symbols = list(set(self.strategy.symbols + list(self.account.positions.keys())))
        
        # 1. 抓取最新毫秒级实时行情
        quotes = self.data_feed.get_realtime_quotes(active_symbols)
        if not quotes:
            logger.warning("未能拉取到实时行情，跳过本次巡检！")
            return []

        # 2. 更新持仓当前市值与账户状态
        self.account.update_quotes(quotes)

        # 3. 风控止损检查
        stop_triggers = self.risk_manager.check_stop_loss_triggers(self.account)
        for sym, reason in stop_triggers.items():
            pos = self.account.positions[sym]
            if pos.available_qty > 0:
                logger.warning(f"🚨 [风控紧急止损触发] 标的 {sym} | 原因: {reason}")
                order = self.broker.sell(
                    symbol=sym,
                    price=quotes[sym]["price"],
                    qty=pos.available_qty,
                    symbol_name=pos.symbol_name,
                    strategy_name="Risk_Stop_Loss",
                    remark=reason
                )
                if order:
                    executed_orders.append(order)

        # 4. 准备策略所需的近期历史 K 线数据 (近 60 个交易日)
        data_dict: Dict[str, pd.DataFrame] = {}
        for sym in self.strategy.symbols:
            # 抓取日线数据
            df = self.data_feed.get_history_bars(
                symbol=sym,
                start_date=(datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y%m%d")
            )
            if not df.empty:
                data_dict[sym] = df

        # 5. 策略生成交易信号
        signals: List[Signal] = self.strategy.generate_signals(
            data_dict=data_dict,
            account=self.account,
            realtime_quotes=quotes
        )

        if not signals:
            logger.info("当前各技术指标未触发新的买卖信号，保持现有仓位。")
        else:
            logger.info(f"策略生成 {len(signals)} 个交易信号！")

        # 6. 先执行卖出，后执行买入
        sell_signals = [s for s in signals if s.action == "SELL"]
        buy_signals = [s for s in signals if s.action == "BUY"]

        for sig in sell_signals:
            order = self.broker.sell(
                symbol=sig.symbol,
                price=sig.price,
                qty=sig.qty,
                symbol_name=quotes.get(sig.symbol, {}).get("name", ""),
                strategy_name=sig.strategy_name,
                remark=sig.reason
            )
            if order:
                executed_orders.append(order)

        for sig in buy_signals:
            # 下单前风控审查
            passed, msg = self.risk_manager.check_buy_order(self.account, sig.symbol, sig.price, sig.qty)
            if not passed:
                logger.warning(f"风控拦截买单 [{sig.symbol}]: {msg}")
                continue

            order = self.broker.buy(
                symbol=sig.symbol,
                price=sig.price,
                qty=sig.qty,
                symbol_name=quotes.get(sig.symbol, {}).get("name", ""),
                strategy_name=sig.strategy_name,
                remark=sig.reason
            )
            if order:
                executed_orders.append(order)

        # 7. 更新最新市值并记录快照
        self.account.update_quotes(quotes)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_pnl = self.account.total_equity - self.account.initial_cash
        cum_ret = self.account.total_return_ratio
        self.db.record_snapshot(
            date_str=today_str,
            total_equity=self.account.total_equity,
            cash=self.account.cash,
            market_value=self.account.market_value,
            daily_pnl=daily_pnl,
            cum_return=cum_ret
        )

        # 打印当前账户资产摘要
        self.account.print_summary()
        return executed_orders

    def run_daily_settlement(self):
        """执行每日收盘 T+1 结算"""
        logger.info("执行每日收盘 T+1 结算...")
        self.account.settle_daily_t_plus_1()

    def start_loop(self, interval_seconds: int = 60):
        """盘中自动循环监控交易"""
        logger.info(f"启动自动模拟盘交易引擎，轮询间隔: {interval_seconds} 秒 (按 Ctrl+C 退出)")
        try:
            while True:
                if self.is_market_hours():
                    self.run_step()
                else:
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"\r[{now}] 当前非 A 股开盘交易时段 (9:30-11:30, 13:00-15:00)，等待开盘...", end="", flush=True)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("模拟盘自动巡检已停止。")
