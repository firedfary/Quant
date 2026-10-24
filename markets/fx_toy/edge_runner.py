"""
Edge 自动化直控引擎 (基于 Chrome DevTools Protocol 原生通信)
Edge Automation Driver for FX Simulation Game
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import time
import asyncio
import tempfile
import subprocess
import requests
from typing import Dict, Any, Optional
import websockets

from markets.fx_toy.config import (
    GAME_URL, DEBUG_PORT, DEFAULT_SYMBOLS, normalize_symbol
)
from utils.logger import get_logger

logger = get_logger("EdgeRunner")

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
]

def find_edge_path() -> str:
    for path in EDGE_PATHS:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("未在标准路径中找到 Microsoft Edge 浏览器 (msedge.exe)")

class EdgeRunner:
    """
    负责启动独立 Edge 实例并通过 WebSocket / CDP 协议直接读写游戏状态
    """
    def __init__(self, debug_port: int = DEBUG_PORT, url: str = GAME_URL):
        self.debug_port = debug_port
        self.url = url
        self.ws_url: Optional[str] = None
        self.msg_id = 0
        self.user_data_dir = os.path.join(tempfile.gettempdir(), "edge_quant_toy_profile")

    def launch_browser(self):
        """拉起独立的 Edge 浏览器，与用户日常使用的 Edge 完全隔离"""
        edge_bin = find_edge_path()
        logger.info(f"正在启动独立 Edge 实例: {edge_bin} (调试端口: {self.debug_port})")

        # 检查端口是否已开
        try:
            r = requests.get(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=1)
            if r.status_code == 200:
                logger.info("检测到已存在调试实例，直接复用连接...")
                return
        except Exception:
            pass

        cmd = [
            edge_bin,
            "--guest",                             # 开启访客模式，避免登录与同步弹窗
            "--disable-sync",                      # 禁用账号同步与提示
            "--disable-features=OptimizationHints,EdgeFre,msEdgeSignInPromo",
            f"--remote-debugging-port={self.debug_port}",
            f"--remote-allow-origins=*",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            self.url
        ]
        subprocess.Popen(cmd)

        # 等待端口就绪
        for _ in range(15):
            time.sleep(1)
            try:
                r = requests.get(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=1)
                if r.status_code == 200:
                    logger.info("Edge 浏览器已就绪并开放 CDP 端口。")
                    break
            except Exception:
                continue
        else:
            raise TimeoutError("启动 Edge 超时，未能在指定端口检测到调试接口。")

        # 预热与弹窗跳过 (新手引导弹窗)
        time.sleep(3)
        try:
            dismiss_js = """
            (() => {
                try {
                    localStorage.setItem('fx-heartbeat-intro-v2', '1');
                    document.getElementById('veteranBtn')?.click();
                    document.getElementById('welcome')?.classList.add('hidden');
                } catch(e) {}
            })()
            """
            asyncio.run(self.evaluate(dismiss_js))
        except Exception as e:
            logger.debug(f"跳过新手弹窗提示: {e}")

    def get_target_ws_url(self) -> str:
        """从 CDP 接口查找游戏页面的 WebSocket 调试 URL (优先匹配 bilibilitoy 内核/iframe)"""
        r = requests.get(f"http://127.0.0.1:{self.debug_port}/json/list", timeout=3)
        pages = r.json()
        
        # 1. 优先寻找真实承载游戏本体的 iframe 或 bilibilitoy 目标
        for page in pages:
            url = page.get("url", "")
            if "bilibilitoy.com" in url:
                return page["webSocketDebuggerUrl"]

        # 2. 其次寻找 iframe 类型的 Target
        for page in pages:
            if page.get("type") == "iframe" and "fx-simple" in page.get("url", ""):
                return page["webSocketDebuggerUrl"]

        # 3. 寻找标题或 URL 匹配的 Page
        for page in pages:
            url = page.get("url", "")
            title = page.get("title", "")
            if "fx-simple" in url or "外汇模拟" in title:
                return page["webSocketDebuggerUrl"]

        for page in pages:
            if page.get("type") == "page":
                return page["webSocketDebuggerUrl"]

        raise RuntimeError("未在 Edge 实例中找到可用的页面 Target")

    async def evaluate(self, js_expr: str) -> Any:
        """通过 CDP 执行一段 JavaScript 表达式并返回结果"""
        ws_url = self.get_target_ws_url()
        async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
            self.msg_id += 1
            payload = {
                "id": self.msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js_expr,
                    "returnByValue": True,
                    "awaitPromise": True
                }
            }
            await ws.send(json.dumps(payload))
            raw_resp = await ws.recv()
            resp = json.loads(raw_resp)
            if "result" in resp and "result" in resp["result"]:
                val = resp["result"]["result"].get("value")
                return val
            return resp

    async def get_state(self) -> Dict[str, Any]:
        """抓取当前账户、行情及持仓快照"""
        js = """
        (() => {
            const getTxt = id => document.getElementById(id)?.innerText?.trim() || "";
            return {
                pair: getTxt('pairTitle') || "EUR / USD",
                price: parseFloat(getTxt('currentPrice')) || 0.0,
                priceChange: getTxt('priceChange'),
                equity: getTxt('equity'),
                cash: getTxt('cash'),
                floating: getTxt('floating'),
                usedMargin: getTxt('usedMargin'),
                debt: getTxt('debt'),
                positionCount: parseInt(getTxt('positionCount')) || 0,
                positionsHtml: document.getElementById('positions')?.innerText?.slice(0, 300) || "暂无持仓"
            };
        })()
        """
        return await self.evaluate(js)

    async def place_trade(self, side: str = "long", margin: float = 50.0, leverage: int = 20) -> Dict[str, Any]:
        """
        通过点击原生按钮执行交易
        :param side: 'long' (做多) 或 'short' (做空)
        :param margin: 保证金 ($10 ~ $10,000)
        :param leverage: 杠杆 (1 ~ 100)
        """
        js = f"""
        (() => {{
            // 1. 设置保证金
            const mInput = document.getElementById('marginInput');
            if (mInput) {{
                mInput.value = '{margin}';
                mInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            // 2. 设置杠杆
            const lInput = document.getElementById('leverageRange');
            if (lInput) {{
                lInput.value = '{leverage}';
                lInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            // 3. 点击下单按钮
            const btnId = '{side.lower()}' === 'long' ? 'longBtn' : 'shortBtn';
            const btn = document.getElementById(btnId);
            if (!btn) return {{ success: false, message: '未找到开仓按钮: ' + btnId }};
            btn.click();
            return {{
                success: true,
                action: '{side.upper()}',
                margin: {margin},
                leverage: {leverage},
                price: document.getElementById('currentPrice')?.innerText
            }};
        }})()
        """
        return await self.evaluate(js)

    async def close_first_position(self) -> Dict[str, Any]:
        """平掉当前第一笔持仓"""
        js = """
        (() => {
            const posContainer = document.getElementById('positions');
            if (!posContainer) return { success: false, message: '无持仓容器' };
            const closeBtn = posContainer.querySelector('button');
            if (!closeBtn) return { success: false, message: '无可用平仓按钮' };
            closeBtn.click();
            return { success: true, message: '已触发平仓' };
        })()
        """
        return await self.evaluate(js)

def main():
    runner = EdgeRunner()
    runner.launch_browser()
    time.sleep(2)
    
    state = asyncio.run(runner.get_state())
    print("\n" + "="*50)
    print("【FX 简单!】Edge 游戏状态实时捕获:")
    print(f"  当前货币对 : {state.get('pair')}")
    print(f"  当前实时汇率: {state.get('price')} ({state.get('priceChange')})")
    print(f"  账户总权益 : {state.get('equity')}")
    print(f"  可用余额   : {state.get('cash')}")
    print(f"  持仓笔数   : {state.get('positionCount')}")
    print("="*50 + "\n")

    if "--trade" in sys.argv:
        print(">>> 正在执行自动开仓测试 (买入做多 EUR/USD, 保证金 $50, 杠杆 20x)...")
        res = asyncio.run(runner.place_trade(side="long", margin=50.0, leverage=20))
        print("开仓结果:", res)
        time.sleep(2)
        new_state = asyncio.run(runner.get_state())
        print(f"下单后持仓状态: {new_state.get('positionsHtml')}")

if __name__ == "__main__":
    main()
