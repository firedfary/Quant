"""
多市场量化交易系统综合管理主控台
Interactive Command Center for Multi-Market Quantitative Trading (A-Share & Crypto)
"""

import sys
import datetime
from config import get_market_config
from core.storage import DBManager
from core.account import Account
from core.base_data_feed import BaseDataFeed
from markets.ashare.data_feed import AshareDataFeed
from markets.crypto.data_feed import CryptoDataFeed
from strategies.common.dual_ma_trend import DualMATrendStrategy
from strategies.common.grid_trading import GridTradingStrategy
from strategies.ashare.momentum_rotation import MomentumRotationStrategy
from strategies.crypto.bollinger_breakout import BollingerBreakoutStrategy
from engines.backtest_engine import BacktestEngine
from engines.paper_engine import PaperTradingEngine

# 当前交互会话所选市场 (默认 A 股)
CURRENT_MARKET = "ashare"

def get_current_cfg():
    return get_market_config(CURRENT_MARKET)

def show_menu():
    cfg = get_current_cfg()
    curr_name = "【 A 股 / ETF 模拟量化系统 】" if CURRENT_MARKET == "ashare" else "【 币安 (Binance) 加密货币量化系统 】"
    print(f"""
==========================================================
        ★ 开源量化交易系统 (多市场版) ★
        当前激活市场: {curr_name}
        基准货币: {cfg.CURRENCY} | 默认本金: {cfg.INITIAL_CASH:,.2f} {cfg.CURRENCY}
==========================================================
  [1] 查看当前市场账户资产与持仓明细 (Account & Holdings)
  [2] 运行历史策略回测 (Run Strategy Backtests)
  [3] 执行一次实时模拟盘撮合 (Run Live Paper Trade Step)
  [4] 启动盘中自动循环监控交易 (Start Live Auto-Trade Loop)
  [5] 查看历史成交流水记录 (View Order Execution History)
  [6] 执行日终结算 (Daily Settlement / T+1)
  [7] 重置当前市场模拟账户 (Reset Capital)
  [M] 切换交易市场 (Switch Market: A-Share <=> Crypto)
  [0] 退出系统 (Exit)
==========================================================
    """)

def view_account():
    cfg = get_current_cfg()
    db = DBManager(db_path=cfg.DB_PATH, initial_cash=cfg.INITIAL_CASH)
    acc = Account(db=db, initial_cash=cfg.INITIAL_CASH, currency=cfg.CURRENCY)
    if acc.positions:
        feed: BaseDataFeed = CryptoDataFeed() if CURRENT_MARKET == "crypto" else AshareDataFeed()
        quotes = feed.get_realtime_quotes(list(acc.positions.keys()))
        if quotes:
            acc.update_quotes(quotes)
    acc.print_summary()

def run_backtest_interactive():
    cfg = get_current_cfg()
    print(f"\n--- 【{CURRENT_MARKET.upper()}】可选回测策略 ---")
    if CURRENT_MARKET == "crypto":
        print("  1. 币安动态等比网格策略 (Grid Trading) - 推荐")
        print("  2. 布林带波动率突破策略 (Bollinger Breakout)")
        print("  3. EMA 趋势双均线突破策略 (Trend Following)")
        choice = input("请选择策略编号 [默认 1]: ").strip() or "1"
        sym = input("请输入加密货币代码 (如 BTCUSDT, ETHUSDT) [默认 BTCUSDT]: ").strip().upper() or "BTCUSDT"
        start_date = input("请输入回测起始日期 (如 20230101) [默认 20240101]: ").strip() or "20240101"

        if choice == "2":
            strat = BollingerBreakoutStrategy(symbols=[sym], qty_precision=4)
        elif choice == "3":
            strat = DualMATrendStrategy(symbols=[sym], lot_size=None, qty_precision=4)
        else:
            strat = GridTradingStrategy(symbol=sym, grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)
    else:
        print("  1. 核心资产动量轮动策略 (ETF Momentum Rotation) - 推荐")
        print("  2. EMA 趋势双均线突破策略 (Trend Following)")
        print("  3. 自适应 ETF 网格交易策略 (Grid Trading)")
        choice = input("请选择策略编号 [默认 1]: ").strip() or "1"
        start_date = input("请输入回测起始日期 (如 20230101) [默认 20230101]: ").strip() or "20230101"

        if choice == "2":
            strat = DualMATrendStrategy(symbols=["513100", "510300"], lot_size=100)
        elif choice == "3":
            strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0, lot_size=100)
        else:
            strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = BacktestEngine(
        strategy=strat,
        start_date=start_date,
        market=CURRENT_MARKET
    )
    results = engine.run()
    if "chart_path" in results:
        print(f"\n✔ 净值曲线图已保存至: {results['chart_path']}")

def run_paper_step():
    print(f"\n--- 【{CURRENT_MARKET.upper()}】选择实盘模拟策略 ---")
    if CURRENT_MARKET == "crypto":
        print("  1. 币安动态网格策略 (BTC/USDT)")
        print("  2. 布林带波动率突破策略")
        print("  3. EMA 趋势双均线突破策略")
        choice = input("请选择策略编号 [默认 1]: ").strip() or "1"
        sym = input("请输入标的代码 [默认 BTCUSDT]: ").strip().upper() or "BTCUSDT"
        if choice == "2":
            strat = BollingerBreakoutStrategy(symbols=[sym], qty_precision=4)
        elif choice == "3":
            strat = DualMATrendStrategy(symbols=[sym], lot_size=None, qty_precision=4)
        else:
            strat = GridTradingStrategy(symbol=sym, grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)
    else:
        print("  1. 核心资产动量轮动策略 (多资产最强龙头)")
        print("  2. EMA 趋势双均线突破策略")
        print("  3. 自适应 ETF 网格交易策略")
        choice = input("请选择策略编号 [默认 1]: ").strip() or "1"
        if choice == "2":
            strat = DualMATrendStrategy(symbols=["513100", "510300"], lot_size=100)
        elif choice == "3":
            strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0, lot_size=100)
        else:
            strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = PaperTradingEngine(strategy=strat, market=CURRENT_MARKET)
    engine.run_step()

def start_paper_loop():
    if CURRENT_MARKET == "crypto":
        strat = GridTradingStrategy(symbol="BTCUSDT", grid_step_pct=0.02, per_grid_amount=800.0, lot_size=None, qty_precision=4)
    else:
        strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])
    
    engine = PaperTradingEngine(strategy=strat, market=CURRENT_MARKET)
    sec = input("请输入轮询检测间隔秒数 [默认 60]: ").strip() or "60"
    engine.start_loop(interval_seconds=int(sec))

def view_order_history():
    cfg = get_current_cfg()
    db = DBManager(db_path=cfg.DB_PATH, initial_cash=cfg.INITIAL_CASH)
    orders = db.get_order_history(limit=20)
    curr = cfg.CURRENCY
    print("\n" + "=" * 80)
    print(f"               【 最近 20 笔成交流水记录 ({CURRENT_MARKET.upper()}) 】")
    print("=" * 80)
    if not orders:
        print(" 暂无成交记录。")
    else:
        print(f" {'成交时间':<19} {'标的代码':<9} {'方向':<5} {'成交价':>9} {'数量':>9} {'成交金额':>11} {'总费用':>8} {'策略/备注'}")
        print("-" * 80)
        for o in orders:
            qty_val = o['qty']
            qty_str = f"{qty_val:.4f}".rstrip("0").rstrip(".") if isinstance(qty_val, float) and not qty_val.is_integer() else str(int(qty_val))
            print(f" {o['created_at']:<19} {o['symbol']:<9} {o['action']:<5} {o['deal_price']:>9.3f} "
                  f"{qty_str:>9} {o['deal_amount']:>10.2f} {curr} {o['total_cost']:>7.2f} {o.get('remark', '')[:20]}")
    print("=" * 80 + "\n")

def reset_account_interactive():
    cfg = get_current_cfg()
    confirm = input(f"⚠️ 确定要重置【{CURRENT_MARKET.upper()}】模拟账户吗？所有持仓和订单流水将被清空！(y/N): ").strip().lower()
    if confirm == "y":
        db = DBManager(db_path=cfg.DB_PATH, initial_cash=cfg.INITIAL_CASH)
        db.reset_account(cfg.INITIAL_CASH)
        print(f"✔ 【{CURRENT_MARKET.upper()}】账户已成功重置！当前本金: {cfg.INITIAL_CASH:,.2f} {cfg.CURRENCY}")
    else:
        print("已取消重置操作。")

def switch_market_interactive():
    global CURRENT_MARKET
    print("\n--- 切换交易市场 ---")
    print("  1. A 股 / ETF 场内模拟盘 (T+1, CNY)")
    print("  2. 币安 (Binance) 加密货币模拟盘 (7x24, T+0, USDT)")
    c = input("请选择目标市场编号: ").strip()
    if c == "2":
        CURRENT_MARKET = "crypto"
        print("✔ 已切换到: 币安 (Binance) 加密货币量化子系统。")
    elif c == "1":
        CURRENT_MARKET = "ashare"
        print("✔ 已切换到: A 股 / ETF 场内量化子系统。")
    else:
        print("输入无效，保持当前市场。")

def main():
    while True:
        show_menu()
        choice = input("请输入功能指令编号: ").strip()
        if choice == "1":
            view_account()
        elif choice == "2":
            run_backtest_interactive()
        elif choice == "3":
            run_paper_step()
        elif choice == "4":
            start_paper_loop()
        elif choice == "5":
            view_order_history()
        elif choice == "6":
            PaperTradingEngine(
                strategy=MomentumRotationStrategy() if CURRENT_MARKET == "ashare" else GridTradingStrategy(symbol="BTCUSDT"),
                market=CURRENT_MARKET
            ).run_daily_settlement()
        elif choice == "7":
            reset_account_interactive()
        elif choice.upper() == "M":
            switch_market_interactive()
        elif choice == "0":
            print("\n感谢使用量化交易系统，祝交易顺利！再见！\n")
            sys.exit(0)
        else:
            print("无效的指令，请重新输入。")

if __name__ == "__main__":
    main()
