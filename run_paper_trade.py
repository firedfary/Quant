"""
实盘模拟交易启动脚本
Run Live Paper Trading
"""

import argparse
from strategies.dual_ma_trend import DualMATrendStrategy
from strategies.grid_trading import GridTradingStrategy
from strategies.momentum_rotation import MomentumRotationStrategy
from engines.paper_engine import PaperTradingEngine

def main():
    parser = argparse.ArgumentParser(description="实盘模拟盘运行入口")
    parser.add_argument("--strategy", type=str, default="rotation", choices=["trend", "grid", "rotation"], help="选择实盘策略")
    parser.add_argument("--loop", action="store_true", help="是否启动后台循环监听模式")
    parser.add_argument("--interval", type=int, default=60, help="循环监听秒数间隔 (默认60秒)")
    parser.add_argument("--settle", action="store_true", help="执行收盘 T+1 结算")
    args = parser.parse_args()

    if args.strategy == "trend":
        strat = DualMATrendStrategy(symbols=["513100", "510300"])
    elif args.strategy == "grid":
        strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0)
    else:
        strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = PaperTradingEngine(strategy=strat)

    if args.settle:
        engine.run_daily_settlement()
    elif args.loop:
        engine.start_loop(interval_seconds=args.interval)
    else:
        # 单次执行：抓取当前真实行情、生成信号、模拟撮合成交并打印最新账户状态
        engine.run_step()

if __name__ == "__main__":
    main()
