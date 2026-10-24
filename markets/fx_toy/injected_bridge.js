/**
 * FX 简单! 浏览器端 WebSocket 全双工网桥脚本
 * 适用环境：bilibilitoy.com 独立纯净游戏页面
 */
(function initFxBridge() {
    console.log("%c[FX-Bridge] 正在初始化本地量化网桥连接...", "color: #108ee9; font-weight: bold;");

    const WS_URL = "ws://127.0.0.1:8765";
    let ws = null;
    let reconnectTimer = null;

    function connect() {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log("%c[FX-Bridge] 成功连接至本地 Python 量化交易框架！", "color: #52c41a; font-weight: bold;");
            if (reconnectTimer) clearInterval(reconnectTimer);
            sendAccountSync();
        };

        ws.onmessage = (event) => {
            try {
                const cmd = JSON.parse(event.data);
                handleCommand(cmd);
            } catch (err) {
                console.error("[FX-Bridge] 解析指令失败:", err);
            }
        };

        ws.onclose = () => {
            console.warn("[FX-Bridge] 与本地 Python 服务连接断开，5秒后自动尝试重连...");
            if (!reconnectTimer) {
                reconnectTimer = setInterval(connect, 5000);
            }
        };

        ws.onerror = (err) => {
            console.error("[FX-Bridge] WebSocket 发生异常:", err);
        };
    }

    // 向上游 Python 推送 TICK 行情
    function sendTick() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const priceEl = document.getElementById('currentPrice');
        const pairEl = document.getElementById('pairTitle');
        const price = parseFloat(priceEl?.innerText?.trim());
        if (!isNaN(price) && price > 0) {
            ws.send(JSON.stringify({
                type: "TICK",
                symbol: pairEl?.innerText?.trim() || "EUR / USD",
                price: price,
                change: document.getElementById('priceChange')?.innerText?.trim() || "",
                timestamp: Date.now() / 1000
            }));
        }
    }

    // 向上游 Python 同步账户与持仓资产
    function sendAccountSync() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({
            type: "ACCOUNT_SYNC",
            equity: document.getElementById('equity')?.innerText?.trim() || "",
            cash: document.getElementById('cash')?.innerText?.trim() || "",
            floating: document.getElementById('floating')?.innerText?.trim() || "",
            usedMargin: document.getElementById('usedMargin')?.innerText?.trim() || "",
            debt: document.getElementById('debt')?.innerText?.trim() || "",
            positionsCount: parseInt(document.getElementById('positionCount')?.innerText?.trim() || "0")
        }));
    }

    // 处理来自 Python 的下行执行指令
    function handleCommand(cmd) {
        console.log("[FX-Bridge] 执行量化指令:", cmd);
        if (cmd.action === "ORDER") {
            const margin = cmd.margin || 50;
            const leverage = cmd.leverage || 20;
            const side = (cmd.side || "BUY").toUpperCase();

            const mInput = document.getElementById('marginInput');
            if (mInput) {
                mInput.value = margin;
                mInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            const lInput = document.getElementById('leverageRange');
            if (lInput) {
                lInput.value = leverage;
                lInput.dispatchEvent(new Event('input', { bubbles: true }));
            }

            const btnId = side === "BUY" ? "longBtn" : "shortBtn";
            const btn = document.getElementById(btnId);
            if (btn) {
                btn.click();
                console.log(`[FX-Bridge] 已触发开仓点击: ${side} 保证金=${margin} 杠杆=${leverage}x`);
                setTimeout(sendAccountSync, 500);
            }
        } else if (cmd.action === "CLOSE") {
            const pos = document.getElementById('positions');
            const closeBtn = pos?.querySelector('button');
            if (closeBtn) {
                closeBtn.click();
                console.log("[FX-Bridge] 已触发平仓点击");
                setTimeout(sendAccountSync, 500);
            }
        }
    }

    // 定时轮询发送 TICK 与资产
    setInterval(sendTick, 1500);
    setInterval(sendAccountSync, 5000);

    // 监听突发市场快讯
    const newsEl = document.getElementById('newsFloat');
    if (newsEl) {
        const obs = new MutationObserver(() => {
            if (!newsEl.classList.contains('hidden') && ws?.readyState === WebSocket.OPEN) {
                const title = document.getElementById('nfTitle')?.innerText?.trim();
                const body = document.getElementById('nfBody')?.innerText?.trim();
                ws.send(JSON.stringify({
                    type: "NEWS",
                    headline: title,
                    body: body,
                    timestamp: Date.now() / 1000
                }));
            }
        });
        obs.observe(newsEl, { attributes: true, attributeFilter: ['class'] });
    }

    // 启动初始连接
    connect();
})();
