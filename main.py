"""
量化交易系统综合管理主控台
Interactive Command Center for Quantitative Trading System
"""

import sys
import datetime
from config import INITIAL_CASH
from core.storage import DBManager
from core.account import Account
from core.data_feed import DataFeed
from strategies.dual_ma_trend import DualMATrendStrategy
from strategies.grid_trading import GridTradingStrategy
from strategies.momentum_rotation import MomentumRotationStrategy
from engines.backtest_engine import BacktestEngine
from engines.paper_engine import PaperTradingEngine

def show_menu():
    print("""
==========================================================
        ★ 开源量化交易系统 (20,000元模拟资金) ★
==========================================================
  [1] 查看模拟账户资产与持仓明细 (Account & Holdings)
  [2] 运行历史策略回测 (Run Strategy Backtests)
  [3] 执行一次实时模拟盘撮合 (Run Live Paper Trade Step)
  [4] 启动盘中自动循环监控交易 (Start Live Auto-Trade Loop)
  [5] 查看历史成交流水记录 (View Order Execution History)
  [6] 执行 T+1 日终结算 (Daily Settlement)
  [7] 重置模拟账户为 20,000 元 (Reset Capital)
  [0] 退出系统 (Exit)
==========================================================
    """)

def view_account():
    db = DBManager()
    acc = Account(db=db)
    # 尝试拉取当前最新市价刷新持仓
    if acc.positions:
        df_feed = DataFeed()
        quotes = df_feed.get_realtime_quotes(list(acc.positions.keys()))
        acc.update_quotes(quotes)
    acc.print_summary()

def run_backtest_interactive():
    print("\n--- 可选回测策略 ---")
    print("  1. 核心资产动量轮动策略 (ETF Momentum Rotation) - 推荐")
    print("  2. EMA 趋势双均线突破策略 (Trend Following)")
    print("  3. 自适应 ETF 网格交易策略 (Grid Trading)")
    choice = input("请选择策略编号 [默认 1]: ").strip() or "1"

    start_date = input("请输入回测起始日期 (如 20230101) [默认 20230101]: ").strip() or "20230101"

    if choice == "2":
        strat = DualMATrendStrategy(symbols=["513100", "510300"])
    elif choice == "3":
        strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0)
    else:
        strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = BacktestEngine(
        strategy=strat,
        start_date=start_date,
        initial_cash=INITIAL_CASH
    )
    results = engine.run()
    if "chart_path" in results:
        print(f"\n✔ 净值曲线图已保存至: {results['chart_path']}")

def run_paper_step():
    print("\n--- 选择实盘模拟策略 ---")
    print("  1. 核心资产动量轮动策略 (多资产最强龙头)")
    print("  2. EMA 趋势双均线突破策略")
    print("  3. 自适应 ETF 网格交易策略")
    choice = input("请选择策略编号 [默认 1]: ").strip() or "1"

    if choice == "2":
        strat = DualMATrendStrategy(symbols=["513100", "510300"])
    elif choice == "3":
        strat = GridTradingStrategy(symbol="510880", grid_step_pct=0.015, per_grid_amount=2500.0)
    else:
        strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])

    engine = PaperTradingEngine(strategy=strat)
    engine.run_step()

def start_paper_loop():
    strat = MomentumRotationStrategy(symbols=["513100", "510300", "518880", "510880"])
    engine = PaperTradingEngine(strategy=strat)
    sec = input("请输入轮询检测间隔秒数 [默认 60]: ").strip() or "60"
    engine.start_loop(interval_seconds=int(sec))

def view_order_history():
    db = DBManager()
    orders = db.get_order_history(limit=20)
    print("\n" + "=" * 80)
    print("                          【 最近 20 笔成交流水记录 】")
    print("=" * 80)
    if not orders:
        print(" 暂无成交记录。")
    else:
        print(f" {'成交时间':<19} {'标的代码':<8} {'方向':<5} {'成交价':>7} {'数量':>6} {'成交金额':>10} {'总税费':>7} {'策略/备注'}")
        print("-" * 80)
        for o in orders:
            print(f" {o['created_at']:<19} {o['symbol']:<8} {o['action']:<5} {o['deal_price']:>7.3f} "
                  f"{o['qty']:>6} ¥{o['deal_amount']:>9.2f} ¥{o['total_cost']:>6.2f} {o.get('remark', '')[:25]}")
    print("=" * 80 + "\n")

def reset_account_interactive():
    confirm = input("⚠️ 确定要重置模拟账户吗？所有持仓和订单流水将被清空！(y/N): ").strip().lower()
    if confirm == "y":
        db = DBManager()
        db.reset_account(INITIAL_CASH)
        print(f"✔ 账户已成功重置！当前本金: ¥{INITIAL_CASH:,.2f}")
    else:
        print("已取消重置操作。")

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
            PaperTradingEngine(strategy=MomentumRotationStrategy()).run_daily_settlement()
            print("✔ T+1 结算完成！")
        elif choice == "7":
            reset_account_interactive()
        elif choice == "0":
            print("\n感谢使用量化交易系统，祝交易顺利！再见！\n")
            sys.exit(0)
        else:
            print("无效的指令，请重新输入。")

if __name__ == "__main__":
    main()
