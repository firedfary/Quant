"""
策略回测启动脚本
Run Strategy Backtesting
"""

import sys
import argparse
from strategies.dual_ma_trend import DualMATrendStrategy
from strategies.grid_trading import GridTradingStrategy
from strategies.momentum_rotation import MomentumRotationStrategy
from engines.backtest_engine import BacktestEngine
from config import INITIAL_CASH

def main():
    parser = argparse.ArgumentParser(description="量化策略历史回测引擎")
    parser.add_argument("--strategy", type=str, default="rotation", choices=["trend", "grid", "rotation"], help="选择策略: trend(双均线趋势), grid(动态网格), rotation(动量轮动)")
    parser.add_argument("--start", type=str, default="20230101", help="回测起始日期 (YYYYMMDD)")
    parser.add_argument("--end", type=str, default=None, help="回测结束日期 (YYYYMMDD，默认至今)")
    parser.add_argument("--cash", type=float, default=INITIAL_CASH, help="初始资金 (默认20000元)")
    args = parser.parse_args()

    if args.strategy == "trend":
        strat = DualMATrendStrategy(symbols=["513100", "510300"])
    elif args.strategy == "grid":
        strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0)
    else:
        strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = BacktestEngine(
        strategy=strat,
        start_date=args.start,
        end_date=args.end,
        initial_cash=args.cash
    )
    results = engine.run()

    if "chart_path" in results:
        print(f"\n✔ 绩效走势图已生成: {results['chart_path']}")

if __name__ == "__main__":
    main()
