"""
外汇小游戏 WebSocket 双向通信服务
WebSocket Bridge Server for FX Toy Market
"""

import asyncio
import json
from typing import Dict, Any, Set
import websockets
from markets.fx_toy.config import WS_PORT
from utils.logger import get_logger

logger = get_logger("FxBridgeServer")

class FxBridgeServer:
    def __init__(self, port: int = WS_PORT):
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.latest_tick: Dict[str, Any] = {}
        self.latest_account: Dict[str, Any] = {}
        self.server = None

    async def register(self, ws):
        self.clients.add(ws)
        logger.info(f"Edge 浏览器网桥已连接: {ws.remote_address}")

    async def unregister(self, ws):
        self.clients.discard(ws)
        logger.info("Edge 浏览器网桥已断开连接")

    async def handler(self, ws, path=None):
        await self.register(ws)
        try:
            async for message in ws:
                data = json.loads(message)
                msg_type = data.get("type", "")
                if msg_type == "TICK":
                    self.latest_tick = data
                    logger.debug(f"收到 TICK 行情: {data.get('symbol')} -> {data.get('price')}")
                elif msg_type == "ACCOUNT_SYNC":
                    self.latest_account = data
                    logger.info(f"账户资金同步: 净值={data.get('equity')}, 余额={data.get('balance')}")
                elif msg_type == "NEWS":
                    logger.info(f"收到市场突发快讯: 【{data.get('headline')}】")
        except websockets.ConnectionClosed:
            pass
        finally:
            await self.unregister(ws)

    async def send_order(self, order: Dict[str, Any]):
        """向下游 Edge 页面广播下单指令"""
        if not self.clients:
            logger.warning("未检测到连接的 Edge 浏览器客户端，无法下发指令")
            return False
        payload = json.dumps(order)
        await asyncio.gather(*[client.send(payload) for client in self.clients])
        logger.info(f"已向下游 Edge 页面发送指令: {order}")
        return True

    async def start(self):
        self.server = await websockets.serve(self.handler, "127.0.0.1", self.port)
        logger.info(f"FX WebSocket 网桥服务端已启动，监听 ws://127.0.0.1:{self.port}")

def run_server():
    server = FxBridgeServer()
    asyncio.run(server.start())
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    run_server()
