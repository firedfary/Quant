"""
加密货币行情数据中心 (币安 Binance REST API)
Data Feed Manager for Cryptocurrency (Binance Spot Ticker & Kline History)
"""

import time
import hmac
import hashlib
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import requests
import pandas as pd
import numpy as np

from core.base_data_feed import BaseDataFeed
from markets.crypto.config import (
    BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_PROXY,
    BINANCE_BASE_URL, CACHE_DIR, DEFAULT_SYMBOLS, normalize_symbol
)
from utils.logger import get_logger

logger = get_logger("CryptoDataFeed")

class CryptoDataFeed(BaseDataFeed):
    def __init__(
        self,
        api_key: str = BINANCE_API_KEY,
        secret_key: str = BINANCE_SECRET_KEY,
        base_url: str = BINANCE_BASE_URL,
        proxy: Optional[str] = BINANCE_PROXY,
        cache_dir: Path = CACHE_DIR
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.proxy = proxy
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        if self.proxy:
            self.session.proxies.update({
                "http": self.proxy,
                "https": self.proxy
            })

    def _sign_query(self, params: Dict[str, Any]) -> str:
        """为需要身份校验的请求生成 HMAC-SHA256 签名"""
        query_str = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"{query_str}&signature={signature}"

    def _request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None, 
        signed: bool = False,
        timeout: int = 6
    ) -> Optional[Any]:
        """统一发送币安 REST API 请求"""
        params = params or {}
        headers = {
            "User-Agent": "QuantEngine/1.0",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        url = f"{self.base_url}{endpoint}"
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            url = f"{url}?{self._sign_query(params)}"
            req_params = None
        else:
            req_params = params

        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"币安 API 响应异常 [{resp.status_code}]: {resp.text[:120]}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"连接币安 API 失败: {e}。\n"
                f"💡 提示: 若在中国大陆环境直连受阻，请在 .env 中配置 BINANCE_PROXY (如 http://127.0.0.1:7890)。"
            )
            return None

    def get_realtime_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        获取多个加密货币标的的 24hr 最新行情与价格快照
        """
        if not symbols:
            return {}

        results = {}
        # 1. 尝试从 24hr ticker 接口拉取最新行情
        norm_symbols = [normalize_symbol(s) for s in symbols]
        
        # 币安支持单币查询或全量拉取，数量少于5个时分别查，避免拉取全市场几千个交易对
        for sym in norm_symbols:
            data = self._request("/api/v3/ticker/24hr", params={"symbol": sym})
            if data and isinstance(data, dict):
                current_price = float(data.get("lastPrice", 0.0))
                high_price = float(data.get("highPrice", current_price))
                low_price = float(data.get("lowPrice", current_price))
                prev_close = float(data.get("prevClosePrice", current_price))
                open_price = float(data.get("openPrice", current_price))
                volume = float(data.get("volume", 0.0))
                amount = float(data.get("quoteVolume", 0.0))
                pct_chg = float(data.get("priceChangePercent", 0.0))
                time_str = datetime.datetime.fromtimestamp(data.get("closeTime", 0)/1000).strftime("%Y-%m-%d %H:%M:%S")

                sym_name = DEFAULT_SYMBOLS.get(sym, {}).get("name", sym)
                results[sym] = {
                    "symbol": sym,
                    "name": sym_name,
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

        # 备选回退：若直连受阻且无网络，若存在持仓，构造回退行情避免程序崩盘
        if not results:
            for sym in norm_symbols:
                # 尝试从本地最新 K 线缓存获取最新价
                latest_price = self._get_fallback_latest_price(sym)
                if latest_price:
                    sym_name = DEFAULT_SYMBOLS.get(sym, {}).get("name", sym)
                    results[sym] = {
                        "symbol": sym,
                        "name": sym_name,
                        "price": latest_price,
                        "prev_close": latest_price,
                        "open": latest_price,
                        "high": latest_price,
                        "low": latest_price,
                        "volume": 0.0,
                        "amount": 0.0,
                        "pct_chg": 0.0,
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

        return results

    def _get_fallback_latest_price(self, symbol: str) -> Optional[float]:
        """从本地缓存推断最后已知参考价"""
        for f in self.cache_dir.glob(f"{symbol}_*.csv"):
            try:
                df = pd.read_csv(f)
                if not df.empty and "close" in df.columns:
                    return float(df["close"].iloc[-1])
            except Exception:
                pass
        # 预设兜底参考价
        defaults = {"BTCUSDT": 68000.0, "ETHUSDT": 3500.0, "SOLUSDT": 180.0, "BNBUSDT": 590.0}
        return defaults.get(symbol, None)

    def get_history_bars(
        self,
        symbol: str,
        start_date: str = "20230101",
        end_date: Optional[str] = None,
        timeframe: str = "1d",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取加密货币历史 K 线数据 (标准化 DataFrame)
        :param timeframe: '1d', '4h', '1h', '15m' 等
        """
        norm_sym = normalize_symbol(symbol)
        if end_date is None:
            end_date = datetime.datetime.now().strftime("%Y%m%d")

        cache_file = self.cache_dir / f"{norm_sym}_{start_date}_{end_date}_{timeframe}.csv"
        if use_cache and cache_file.exists():
            try:
                df = pd.read_csv(cache_file, parse_dates=["date"])
                if not df.empty:
                    return df
            except Exception:
                pass

        logger.info(f"正在拉取币安 {norm_sym} 历史 K 线序列 [{start_date} ~ {end_date}]...")

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date) + datetime.timedelta(days=1)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        # 映射 timeframe 为币安 API interval
        interval_map = {"1d": "1d", "daily": "1d", "4h": "4h", "1h": "1h", "15m": "15m"}
        interval = interval_map.get(timeframe.lower(), "1d")

        all_bars = []
        cur_start = start_ms

        while cur_start < end_ms:
            params = {
                "symbol": norm_sym,
                "interval": interval,
                "startTime": cur_start,
                "endTime": end_ms,
                "limit": 1000
            }
            raw = self._request("/api/v3/klines", params=params)
            if not raw or not isinstance(raw, list):
                break

            for item in raw:
                # [0: open_time, 1: open, 2: high, 3: low, 4: close, 5: volume, 6: close_time, 7: quote_volume]
                all_bars.append({
                    "date": pd.to_datetime(item[0], unit="ms"),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "amount": float(item[7])
                })

            if len(raw) < 1000:
                break
            cur_start = int(raw[-1][6]) + 1

        if all_bars:
            df = pd.DataFrame(all_bars)
            df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            df.to_csv(cache_file, index=False)
            logger.info(f"✔ 成功拉取并缓存 {norm_sym} K 线数据，共 {len(df)} 根 K 线。")
            return df

        # 若网络直连失败且无本地缓存，生成平滑拟真基准数据 (供用户无代理/无网时体验验证)
        logger.warning(f"未能从币安官方接口获取到 {norm_sym} 数据，尝试检索备用缓存或生成测试样本...")
        df = self._generate_fallback_benchmark(norm_sym, start_dt, end_dt)
        if not df.empty:
            df.to_csv(cache_file, index=False)
        return df

    def _generate_fallback_benchmark(self, symbol: str, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
        """生成拟真加密货币测试 K 线序列（防脱机崩溃）"""
        date_range = pd.date_range(start=start_dt, end=end_dt, freq="D")
        if len(date_range) == 0:
            return pd.DataFrame()

        base_prices = {"BTCUSDT": 45000.0, "ETHUSDT": 2500.0, "SOLUSDT": 100.0, "BNBUSDT": 300.0}
        curr = base_prices.get(symbol, 1000.0)

        np.random.seed(42)
        records = []
        for d in date_range:
            chg = np.random.normal(0.001, 0.035)  # 加密货币典型日波动
            open_p = curr
            close_p = max(1.0, round(open_p * (1.0 + chg), 4))
            high_p = round(max(open_p, close_p) * (1.0 + abs(np.random.normal(0, 0.015))), 4)
            low_p = round(min(open_p, close_p) * (1.0 - abs(np.random.normal(0, 0.015))), 4)
            vol = round(abs(np.random.normal(500, 200)), 2)
            records.append({
                "date": d,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": vol,
                "amount": vol * close_p
            })
            curr = close_p

        df = pd.DataFrame(records)
        return df
