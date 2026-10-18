"""
持久化存储模块 (SQLite)
Storage & Database Manager for Account, Positions, Orders and Daily Snapshots
"""

import sqlite3
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from config import DB_PATH, INITIAL_CASH
from utils.logger import get_logger

logger = get_logger("Storage")

class DBManager:
    def __init__(self, db_path=DB_PATH, initial_cash: float = INITIAL_CASH):
        self.db_path = str(db_path)
        self.initial_cash = float(initial_cash)
        self._shared_conn = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """初始化数据表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 账户总表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                initial_cash REAL NOT NULL,
                cash REAL NOT NULL,
                frozen_cash REAL DEFAULT 0.0,
                total_equity REAL NOT NULL,
                realized_pnl REAL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            )
            """)

            # 2. 持仓明细表 (qty 改为 REAL 以兼容加密货币浮点数)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                symbol_name TEXT,
                total_qty REAL NOT NULL DEFAULT 0.0,
                available_qty REAL NOT NULL DEFAULT 0.0,
                cost_price REAL NOT NULL DEFAULT 0.0,
                current_price REAL NOT NULL DEFAULT 0.0,
                market_value REAL NOT NULL DEFAULT 0.0,
                floating_pnl REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            )
            """)

            # 3. 订单成交记录表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                symbol_name TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                deal_price REAL NOT NULL,
                qty REAL NOT NULL,
                deal_amount REAL NOT NULL,
                commission REAL NOT NULL,
                stamp_tax REAL NOT NULL,
                transfer_fee REAL NOT NULL,
                total_cost REAL NOT NULL,
                strategy_name TEXT,
                remark TEXT,
                created_at TEXT NOT NULL
            )
            """)

            # 4. 每日资产快照表 (用于绘制收益净值曲线)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                date TEXT PRIMARY KEY,
                total_equity REAL NOT NULL,
                cash REAL NOT NULL,
                market_value REAL NOT NULL,
                daily_pnl REAL NOT NULL,
                cum_return REAL NOT NULL
            )
            """)

            # 初始化账户初始记录（如果不存在）
            cursor.execute("SELECT COUNT(*) as count FROM account WHERE id = 1")
            row = cursor.fetchone()
            if row["count"] == 0:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                INSERT INTO account (id, initial_cash, cash, frozen_cash, total_equity, realized_pnl, updated_at)
                VALUES (1, ?, ?, 0.0, ?, 0.0, ?)
                """, (self.initial_cash, self.initial_cash, self.initial_cash, now_str))
                logger.info(f"初始化模拟账户完成，初始资金: {self.initial_cash:,.2f}")

            conn.commit()

    def reset_account(self, initial_cash: Optional[float] = None):
        """重置模拟账户为初始状态"""
        init_c = float(initial_cash) if initial_cash is not None else self.initial_cash
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM daily_snapshots")
            cursor.execute("""
            INSERT OR REPLACE INTO account (id, initial_cash, cash, frozen_cash, total_equity, realized_pnl, updated_at)
            VALUES (1, ?, ?, 0.0, ?, 0.0, ?)
            """, (init_c, init_c, init_c, now_str))
            conn.commit()
            logger.info(f"账户已重置！资金设为: {init_c:,.2f}")

    def load_account(self) -> Dict[str, Any]:
        """获取账户当前状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM account WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {
                "initial_cash": self.initial_cash,
                "cash": self.initial_cash,
                "frozen_cash": 0.0,
                "total_equity": self.initial_cash,
                "realized_pnl": 0.0,
                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def update_account(self, cash: float, frozen_cash: float, total_equity: float, realized_pnl: float):
        """更新账户信息"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE account 
            SET cash = ?, frozen_cash = ?, total_equity = ?, realized_pnl = ?, updated_at = ?
            WHERE id = 1
            """, (cash, frozen_cash, total_equity, realized_pnl, now_str))
            conn.commit()

    def load_positions(self) -> Dict[str, Dict[str, Any]]:
        """获取当前所有持仓"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE total_qty > 0")
            rows = cursor.fetchall()
            return {row["symbol"]: dict(row) for row in rows}

    def save_position(self, pos: Dict[str, Any]):
        """保存或更新单个标的持仓"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            t_qty = float(pos["total_qty"])
            if t_qty <= 0:
                cursor.execute("DELETE FROM positions WHERE symbol = ?", (pos["symbol"],))
            else:
                cursor.execute("""
                INSERT OR REPLACE INTO positions 
                (symbol, symbol_name, total_qty, available_qty, cost_price, current_price, market_value, floating_pnl, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pos["symbol"], pos.get("symbol_name", ""),
                    t_qty, float(pos["available_qty"]),
                    float(pos["cost_price"]), float(pos.get("current_price", pos["cost_price"])),
                    float(pos.get("market_value", 0.0)), float(pos.get("floating_pnl", 0.0)),
                    now_str
                ))
            conn.commit()

    def record_order(self, order_data: Dict[str, Any]):
        """记录成交订单"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO orders 
            (order_id, symbol, symbol_name, action, status, deal_price, qty, deal_amount, 
             commission, stamp_tax, transfer_fee, total_cost, strategy_name, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_data["order_id"], order_data["symbol"], order_data.get("symbol_name", ""),
                order_data["action"], order_data["status"], float(order_data["deal_price"]),
                float(order_data["qty"]), float(order_data["deal_amount"]), float(order_data["commission"]),
                float(order_data["stamp_tax"]), float(order_data["transfer_fee"]), float(order_data["total_cost"]),
                order_data.get("strategy_name", ""), order_data.get("remark", ""),
                order_data.get("created_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ))
            conn.commit()

    def get_order_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近成交流水"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def record_snapshot(self, date_str: str, total_equity: float, cash: float, market_value: float, daily_pnl: float, cum_return: float):
        """记录每日资产净值快照"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO daily_snapshots (date, total_equity, cash, market_value, daily_pnl, cum_return)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (date_str, total_equity, cash, market_value, daily_pnl, cum_return))
            conn.commit()

    def get_snapshots(self) -> List[Dict[str, Any]]:
        """获取所有历史快照用于作图分析"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_snapshots ORDER BY date ASC")
            return [dict(r) for r in cursor.fetchall()]
