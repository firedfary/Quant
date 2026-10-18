"""
多市场策略回测启动脚本
Run Strategy Backtesting (A-Share & Crypto)
"""

import sys
import argparse
from strategies.common.dual_ma_trend import DualMATrendStrategy
from strategies.common.grid_trading import GridTradingStrategy
from strategies.ashare.momentum_rotation import MomentumRotationStrategy
from strategies.crypto.bollinger_breakout import BollingerBreakoutStrategy
from engines.backtest_engine import BacktestEngine
from markets.crypto.config import normalize_symbol

def main():
    parser = argparse.ArgumentParser(description="多市场量化策略历史回测引擎")
    parser.add_argument(
        "--market", 
        type=str, 
        default="ashare", 
        choices=["ashare", "crypto"], 
        help="选择市场: ashare(A股/ETF), crypto(币安加密货币)"
    )
    parser.add_argument(
        "--strategy", 
        type=str, 
        default=None, 
        choices=["trend", "grid", "rotation", "bollinger"], 
        help="选择策略: trend(双均线趋势), grid(动态网格), rotation(A股动量轮动), bollinger(币圈布林带突破)"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default=None, 
        help="指定回测标的代码 (如 A股: 510300, 币圈: BTCUSDT)"
    )
    parser.add_argument(
        "--start", 
        type=str, 
        default="20230101", 
        help="回测起始日期 (YYYYMMDD)"
    )
    parser.add_argument(
        "--end", 
        type=str, 
        default=None, 
        help="回测结束日期 (YYYYMMDD，默认至今)"
    )
    parser.add_argument(
        "--cash", 
        type=float, 
        default=None, 
        help="初始本金 (默认自适应: A股 20,000 元, 币圈 5,000 USDT)"
    )
    args = parser.parse_args()

    market = args.market.lower()

    # 策略路由与自适应实例化
    if market == "crypto":
        strat_type = args.strategy or "grid"
        target_sym = normalize_symbol(args.symbol or "BTCUSDT")

        if strat_type == "trend":
            strat = DualMATrendStrategy(symbols=[target_sym], lot_size=None, qty_precision=4)
        elif strat_type == "bollinger":
            strat = BollingerBreakoutStrategy(symbols=[target_sym], qty_precision=4)
        elif strat_type == "rotation":
            print("⚠ 动量轮动目前专为 A 股宽基 ETF 设计，虚拟币系统建议使用 grid 或 bollinger 策略！自动切换为 grid 策略。")
            strat = GridTradingStrategy(symbol=target_sym, grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)
        else: # grid
            strat = GridTradingStrategy(symbol=target_sym, grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)

    else: # ashare
        strat_type = args.strategy or "rotation"
        target_sym = args.symbol or "510880"

        if strat_type == "trend":
            symbols = [args.symbol] if args.symbol else ["513100", "510300"]
            strat = DualMATrendStrategy(symbols=symbols, lot_size=100)
        elif strat_type == "grid":
            strat = GridTradingStrategy(symbol=target_sym, grid_step_pct=0.015, per_grid_amount=2500.0, lot_size=100)
        elif strat_type == "bollinger":
            print("⚠ 布林带突破策略专为高波动加密货币设计，A 股建议使用 rotation 或 trend 策略！自动切换为 trend 策略。")
            strat = DualMATrendStrategy(symbols=[target_sym], lot_size=100)
        else: # rotation
            strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = BacktestEngine(
        strategy=strat,
        start_date=args.start,
        end_date=args.end,
        market=market,
        initial_cash=args.cash
    )
    results = engine.run()

    if "chart_path" in results:
        print(f"\n✔ 绩效走势图已生成: {results['chart_path']}")

if __name__ == "__main__":
    main()
