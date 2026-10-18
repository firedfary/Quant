"""
A 股行情数据管理中心
Data Feed Manager for A-Shares & ETFs (Tencent Quotes & AkShare K-Lines)
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests
import pandas as pd
import akshare as ak
from core.base_data_feed import BaseDataFeed
from markets.ashare.config import CACHE_DIR, is_etf, DEFAULT_SYMBOLS
from utils.logger import get_logger

# 确保在 Windows 控制台下支持 UTF-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = get_logger("AshareDataFeed")

class AshareDataFeed(BaseDataFeed):
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def format_market_code(symbol: str) -> str:
        """格式化为带市场前缀的代码 (sh/sz)"""
        s = str(symbol).strip().lower()
        if s.startswith(('sh', 'sz', 'bj')):
            return s
        if s.startswith(('5', '6', '9')):
            return f"sh{s}"
        elif s.startswith(('0', '1', '2', '3')):
            return f"sz{s}"
        elif s.startswith(('4', '8')):
            return f"bj{s}"
        return f"sh{s}"

    def get_realtime_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        获取多个标的的毫秒级实时行情 (基于腾讯金融接口，高速稳定)
        """
        if not symbols:
            return {}

        formatted_codes = [self.format_market_code(s) for s in symbols]
        url = f"http://qt.gtimg.cn/q={','.join(formatted_codes)}"
        
        results = {}
        try:
            resp = requests.get(url, timeout=5)
            resp.encoding = "gbk"
            lines = resp.text.strip().split(";\n")
            
            for line in lines:
                if not line or "=" not in line:
                    continue
                left, right = line.split("=", 1)
                data_str = right.strip('"\r\n ;')
                parts = data_str.split("~")
                if len(parts) < 35:
                    continue
                
                symbol = parts[2]
                name = parts[1]
                current_price = float(parts[3])
                prev_close = float(parts[4])
                open_price = float(parts[5])
                high_price = float(parts[33]) if parts[33] else current_price
                low_price = float(parts[34]) if parts[34] else current_price
                volume = float(parts[6])  # 成交量(手)
                amount = float(parts[37]) * 10000.0 if parts[37] else 0.0  # 成交额(元)
                pct_chg = float(parts[31]) if parts[31] else 0.0
                time_str = parts[29] if len(parts) > 29 else ""

                if current_price == 0.0:
                    current_price = prev_close

                results[symbol] = {
                    "symbol": symbol,
                    "name": name,
                    "price": current_price,
                    "prev_close": prev_close,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "volume": volume,
                    "amount": amount,
                    "pct_chg": pct_chg,
                    "timestamp": time_str
                }
        except Exception as e:
            logger.error(f"获取 A 股实时行情异常: {e}")

        return results

    def _fetch_from_tencent_kline(self, symbol: str, count: int = 500) -> pd.DataFrame:
        """从腾讯极速接口拉取前复权日K线数据"""
        market_code = self.format_market_code(symbol)
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market_code},day,,,{count},qfq"
        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            target = data.get("data", {}).get(market_code, {})
            bars = target.get("qfqday", target.get("day", []))
            if not bars:
                return pd.DataFrame()

            records = []
            for b in bars:
                records.append({
                    "date": pd.to_datetime(b[0]),
                    "open": float(b[1]),
                    "close": float(b[2]),
                    "high": float(b[3]),
                    "low": float(b[4]),
                    "volume": float(b[5]),
                    "amount": float(b[5]) * float(b[2]) * 100.0
                })
            df = pd.DataFrame(records)
            df = df.sort_values("date").reset_index(drop=True)
            return df
        except Exception as e:
            logger.warning(f"腾讯K线接口获取 {symbol} 失败 ({e})，准备切换备用数据源...")
            return pd.DataFrame()

    def get_history_bars(
        self, 
        symbol: str, 
        start_date: str = "20230101", 
        end_date: Optional[str] = None,
        timeframe: str = "1d",
        adjust: str = "qfq",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取 A 股标的历史日K线数据 (多通道：本地缓存 -> 腾讯毫秒K线 -> AkShare)
        """
        symbol = str(symbol).strip()
        if end_date is None:
            end_date = datetime.datetime.now().strftime("%Y%m%d")
        
        cache_file = self.cache_dir / f"{symbol}_{start_date}_{end_date}_{adjust}.csv"
        if use_cache and cache_file.exists():
            try:
                df = pd.read_csv(cache_file, parse_dates=["date"])
                if not df.empty:
                    return df
            except Exception:
                pass

        logger.info(f"正在拉取 A 股标的 {symbol} 历史日K线数据 [{start_date} ~ {end_date}]...")
        
        # 1. 优先使用极速稳定的腾讯 K 线通道
        df = self._fetch_from_tencent_kline(symbol, count=500)
        if not df.empty:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].reset_index(drop=True)
            if not df.empty:
                df.to_csv(cache_file, index=False)
                return df

        # 2. 备用通道：AkShare
        try:
            if is_etf(symbol):
                raw_df = ak.fund_etf_hist_em(
                    symbol=symbol, 
                    period="daily", 
                    start_date=start_date, 
                    end_date=end_date, 
                    adjust=adjust
                )
            else:
                raw_df = ak.stock_zh_a_hist(
                    symbol=symbol, 
                    period="daily", 
                    start_date=start_date, 
                    end_date=end_date, 
                    adjust=adjust
                )

            if raw_df is not None and not raw_df.empty:
                col_map = {
                    "日期": "date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                    "成交额": "amount"
                }
                df = raw_df.rename(columns=col_map)
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                for c in ["open", "close", "high", "low", "volume", "amount"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                df.to_csv(cache_file, index=False)
                return df
        except Exception as e:
            logger.error(f"AkShare 拉取 {symbol} 历史K线失败: {e}")

        return pd.DataFrame()
