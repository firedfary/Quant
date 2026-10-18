"""
多市场实盘模拟交易启动脚本
Run Live Paper Trading (A-Share & Crypto)
"""

import argparse
from strategies.common.dual_ma_trend import DualMATrendStrategy
from strategies.common.grid_trading import GridTradingStrategy
from strategies.ashare.momentum_rotation import MomentumRotationStrategy
from strategies.crypto.bollinger_breakout import BollingerBreakoutStrategy
from engines.paper_engine import PaperTradingEngine
from markets.crypto.config import normalize_symbol

def main():
    parser = argparse.ArgumentParser(description="多市场实盘模拟交易启动入口")
    parser.add_argument(
        "--market", 
        type=str, 
        default="ashare", 
        choices=["ashare", "crypto"], 
        help="选择交易市场: ashare(A股), crypto(币安加密货币)"
    )
    parser.add_argument(
        "--strategy", 
        type=str, 
        default=None, 
        choices=["trend", "grid", "rotation", "bollinger"], 
        help="选择实盘策略: trend, grid, rotation, bollinger"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default=None, 
        help="指定交易标的代码 (例如 A股: 510880, 币圈: BTCUSDT)"
    )
    parser.add_argument(
        "--loop", 
        action="store_true", 
        help="是否启动后台循环盯盘模式"
    )
    parser.add_argument(
        "--interval", 
        type=int, 
        default=60, 
        help="循环监听秒数间隔 (默认60秒)"
    )
    parser.add_argument(
        "--settle", 
        action="store_true", 
        help="执行日终结算 (A股 T+1 解冻)"
    )
    args = parser.parse_args()

    market = args.market.lower()

    if market == "crypto":
        strat_type = args.strategy or "grid"
        target_sym = normalize_symbol(args.symbol or "BTCUSDT")

        if strat_type == "trend":
            strat = DualMATrendStrategy(symbols=[target_sym], lot_size=None, qty_precision=4)
        elif strat_type == "bollinger":
            strat = BollingerBreakoutStrategy(symbols=[target_sym], qty_precision=4)
        else: # grid
            strat = GridTradingStrategy(symbol=target_sym, grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)

    else: # ashare
        strat_type = args.strategy or "rotation"
        target_sym = args.symbol or "510880"

        if strat_type == "trend":
            strat = DualMATrendStrategy(symbols=[args.symbol] if args.symbol else ["513100", "510300"], lot_size=100)
        elif strat_type == "grid":
            strat = GridTradingStrategy(symbol=target_sym, grid_step_pct=0.015, per_grid_amount=2500.0, lot_size=100)
        else: # rotation
            strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = PaperTradingEngine(strategy=strat, market=market)

    if args.settle:
        engine.run_daily_settlement()
    elif args.loop:
        engine.start_loop(interval_seconds=args.interval)
    else:
        # 单次执行：抓取当前真实行情、生成信号、模拟撮合成交并打印最新账户状态
        engine.run_step()

if __name__ == "__main__":
    main()
