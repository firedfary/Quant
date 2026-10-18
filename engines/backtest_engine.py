"""
事件驱动型历史回测引擎 (多市场支持)
Event-driven Backtesting Engine with Institutional Performance Metrics
"""

import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from config import BASE_DIR, get_market_config
from core.account import Account, Position
from core.storage import DBManager
from core.base_broker import BaseBroker
from core.base_data_feed import BaseDataFeed
from markets.ashare.broker import AshareBroker
from markets.ashare.data_feed import AshareDataFeed
from markets.crypto.broker import CryptoBroker
from markets.crypto.data_feed import CryptoDataFeed
from strategies.base import BaseStrategy
from utils.logger import get_logger

# 设置 matplotlib 支持中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

logger = get_logger("BacktestEngine")

class BacktestEngine:
    def __init__(
        self,
        strategy: BaseStrategy,
        start_date: str = "20230101",
        end_date: Optional[str] = None,
        market: str = "ashare",
        initial_cash: Optional[float] = None,
        slippage: Optional[float] = None,
        broker_class: Optional[Type[BaseBroker]] = None,
        data_feed: Optional[BaseDataFeed] = None
    ):
        self.strategy = strategy
        self.start_date = start_date
        self.end_date = end_date or datetime.datetime.now().strftime("%Y%m%d")
        self.market = market.lower().strip()
        
        # 路由市场规则配置
        market_cfg = get_market_config(self.market)
        self.currency = getattr(market_cfg, "CURRENCY", "CNY")
        self.is_t_plus_1 = getattr(market_cfg, "T_PLUS_1", True)
        self.initial_cash = float(initial_cash) if initial_cash is not None else getattr(market_cfg, "INITIAL_CASH", 20000.0)
        self.slippage = float(slippage) if slippage is not None else getattr(market_cfg, "DEFAULT_SLIPPAGE", 0.001)

        # 实例化行情引擎
        if data_feed is not None:
            self.data_feed = data_feed
        elif self.market in ("crypto", "binance", "coin"):
            self.data_feed = CryptoDataFeed()
        else:
            self.data_feed = AshareDataFeed()

        self.broker_class = broker_class or (CryptoBroker if self.market in ("crypto", "binance", "coin") else AshareBroker)

    def run(self) -> Dict[str, Any]:
        """运行历史回测并输出全套绩效统计"""
        logger.info(f"====== 开始回测策略 [{self.strategy.name}] (市场: {self.market.upper()}) ======")
        logger.info(f"回测区间: {self.start_date} ~ {self.end_date} | 初始本金: {self.initial_cash:,.2f} {self.currency}")

        # 1. 准备所有标的历史数据
        data_dict: Dict[str, pd.DataFrame] = {}
        for sym in self.strategy.symbols:
            df = self.data_feed.get_history_bars(
                symbol=sym,
                start_date=self.start_date,
                end_date=self.end_date
            )
            if df is not None and not df.empty:
                data_dict[sym] = df

        if not data_dict:
            logger.error("未获取到有效的历史数据，回测中止！")
            return {}

        # 统一所有标的的交易日轴 (所有标的日期的并集)
        all_dates = sorted(list(set.union(*[set(df["date"]) for df in data_dict.values()])))
        logger.info(f"总交易日天数: {len(all_dates)} 天")

        # 2. 初始化回测内存隔离账户与经纪商 (使用临时内存SQLite数据库)
        temp_db = DBManager(db_path=":memory:", initial_cash=self.initial_cash)
        temp_account = Account(db=temp_db, initial_cash=self.initial_cash, currency=self.currency)
        temp_account.cash = self.initial_cash
        temp_account.initial_cash = self.initial_cash
        broker = self.broker_class(account=temp_account, db=temp_db, slippage=self.slippage)

        # 记录每日资金与净值序列
        equity_records = []
        trade_logs = []

        # 3. 按交易日推进时间步 (Event-driven Time Step)
        for i, current_date in enumerate(all_dates):
            current_date_str = current_date.strftime("%Y-%m-%d")

            # 准备截至当前日期的历史切片
            current_slice: Dict[str, pd.DataFrame] = {}
            current_prices: Dict[str, Dict[str, Any]] = {}

            for sym, df in data_dict.items():
                sub_df = df[df["date"] <= current_date]
                if not sub_df.empty:
                    current_slice[sym] = sub_df
                    last_row = sub_df.iloc[-1]
                    current_prices[sym] = {
                        "price": float(last_row["close"]),
                        "name": sym
                    }

            # 更新当前持仓市值
            temp_account.update_quotes(current_prices)

            # T+1 日终结算：前一日买入的转为可用 (仅限 A 股，加密货币 T+0 即时可用)
            if self.is_t_plus_1:
                temp_account.settle_daily_t_plus_1()

            # 策略生成交易信号
            signals = self.strategy.generate_signals(
                data_dict=current_slice,
                account=temp_account,
                realtime_quotes=current_prices
            )

            # 执行交易信号 (先卖后买，释放流动性)
            sell_signals = [s for s in signals if s.action == "SELL"]
            buy_signals = [s for s in signals if s.action == "BUY"]

            for sig in sell_signals:
                order = broker.sell(
                    symbol=sig.symbol,
                    price=sig.price,
                    qty=sig.qty,
                    strategy_name=sig.strategy_name,
                    remark=sig.reason
                )
                if order:
                    order["date"] = current_date_str
                    trade_logs.append(order)

            for sig in buy_signals:
                order = broker.buy(
                    symbol=sig.symbol,
                    price=sig.price,
                    qty=sig.qty,
                    strategy_name=sig.strategy_name,
                    remark=sig.reason
                )
                if order:
                    order["date"] = current_date_str
                    trade_logs.append(order)

            # 再次更新持仓市值
            temp_account.update_quotes(current_prices)

            # 记录今日资产
            total_equity = temp_account.total_equity
            equity_records.append({
                "date": current_date,
                "equity": total_equity,
                "cash": temp_account.cash,
                "market_value": temp_account.market_value
            })

        # 4. 计算绩效评价指标
        perf_df = pd.DataFrame(equity_records).set_index("date")
        perf_df["returns"] = perf_df["equity"].pct_change().fillna(0.0)
        perf_df["cum_returns"] = (perf_df["equity"] / self.initial_cash) - 1.0

        # 回撤计算
        perf_df["cum_max"] = perf_df["equity"].cummax()
        perf_df["drawdown"] = (perf_df["equity"] - perf_df["cum_max"]) / perf_df["cum_max"]
        max_drawdown = perf_df["drawdown"].min()

        total_return = (perf_df["equity"].iloc[-1] / self.initial_cash) - 1.0
        days = (all_dates[-1] - all_dates[0]).days
        years = max(days / 365.25, 0.1)
        annualized_return = (1.0 + total_return) ** (1.0 / years) - 1.0

        # 夏普比率 (年化无风险利率取 2.0%)
        daily_rf = 0.02 / 250
        excess_returns = perf_df["returns"] - daily_rf
        sharpe_ratio = np.sqrt(250) * excess_returns.mean() / (perf_df["returns"].std() + 1e-6)

        # 胜率与盈亏比分析
        sell_trades = [t for t in trade_logs if t["action"] == "SELL"]
        win_count = sum(1 for t in sell_trades if t["deal_price"] * t["qty"] > t["total_cost"])
        win_rate = (win_count / len(sell_trades)) if sell_trades else 0.0

        results = {
            "strategy_name": self.strategy.name,
            "market": self.market,
            "currency": self.currency,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_cash": self.initial_cash,
            "final_equity": round(perf_df["equity"].iloc[-1], 2),
            "total_return_pct": round(total_return * 100, 2),
            "annualized_return_pct": round(annualized_return * 100, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "total_trades": len(trade_logs),
            "closed_trades": len(sell_trades),
            "win_rate_pct": round(win_rate * 100, 2),
            "equity_df": perf_df,
            "trade_logs": trade_logs
        }

        # 打印绩效简报
        self._print_report(results)

        # 绘制并保存净值与回撤图
        chart_path = self._plot_performance(perf_df, results)
        results["chart_path"] = chart_path

        return results

    def _print_report(self, res: Dict[str, Any]):
        curr = res["currency"]
        print("\n" + "=" * 58)
        print(f"       【 策略回测绩效评估报告: {res['strategy_name']} ({res['market'].upper()}) 】")
        print("=" * 58)
        print(f" 回测区间:       {res['start_date']} 至 {res['end_date']}")
        print(f" 初始资金:       {res['initial_cash']:>12,.2f} {curr}")
        print(f" 最终资产:       {res['final_equity']:>12,.2f} {curr}")
        print(f" 累计总收益率:   {res['total_return_pct']:>11.2f}%")
        print(f" 年化复合收益率: {res['annualized_return_pct']:>11.2f}%")
        print(f" 最大资产回撤:   {res['max_drawdown_pct']:>11.2f}%")
        print(f" 夏普比率:       {res['sharpe_ratio']:>12.2f}")
        print(f" 总交易成交笔数: {res['total_trades']:>12} 笔")
        print(f" 平仓交易胜率:   {res['win_rate_pct']:>11.2f}%")
        print("=" * 58 + "\n")

    def _plot_performance(self, perf_df: pd.DataFrame, res: Dict[str, Any]) -> str:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        curr = res["currency"]

        # 净值走势
        ax1.plot(perf_df.index, perf_df["equity"], label=f"策略总资产 ({curr})", color="#1f77b4", linewidth=2.0)
        ax1.axhline(self.initial_cash, color="#888888", linestyle="--", alpha=0.7, label=f"初始本金 ({self.initial_cash:,.0f} {curr})")
        ax1.set_title(f"量化策略回测净值走势 [{res['strategy_name']}] ({res['market'].upper()}) | 收益率: {res['total_return_pct']}% | 最大回撤: {res['max_drawdown_pct']}%", fontsize=12, pad=10)
        ax1.set_ylabel(f"账户动态总资产 ({curr})", fontsize=10)
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.legend(loc="upper left")

        # 回撤区域图
        ax2.fill_between(perf_df.index, perf_df["drawdown"] * 100, 0, color="#d62728", alpha=0.35, label="动态回撤 (%)")
        ax2.set_ylabel("回撤幅度 (%)", fontsize=10)
        ax2.set_xlabel("交易日期", fontsize=10)
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend(loc="lower left")

        plt.tight_layout()
        chart_file = BASE_DIR / "data" / f"backtest_{res['market']}_{res['strategy_name']}.png"
        plt.savefig(chart_file, dpi=150)
        plt.close(fig)
        logger.info(f"回测绩效图表已生成并保存至: {chart_file}")
        return str(chart_file)
