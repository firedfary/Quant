# 多市场量化交易系统 (A股 / 场内ETF & 币安加密货币双子系统)

基于**模块化单仓库（Modular Monorepo / Adapter Pattern）**架构设计的跨市场量化交易系统。
系统抽离中立通用的事件驱动回测引擎、模拟盘引擎、风控防线与账户模型，并通过适配器分别接入 **A 股/场内 ETF 市场** 与 **币安（Binance）加密货币市场**。

---

## 一、 系统架构全景

```
d:/Quant/
├── .env                      # 私密配置 (Binance API Key/Secret, 代理端口 - 严禁提交)
├── .env.example              # 环境变量配置模板
├── config.py                 # 全局配置中枢与多市场配置路由
├── requirements.txt          # 项目依赖清单
│
├── core/                     # 【通用核心内核】完全独立于具体市场
│   ├── base_broker.py        # 撮合经纪商抽象基类 (约定费用计算、买入、卖出接口)
│   ├── base_data_feed.py     # 行情数据抽象基类 (约定实时行情、历史K线接口)
│   ├── account.py            # 通用账户与持仓模型 (支持浮点数仓位、CNY/USDT 货币显示)
│   ├── risk_manager.py       # 通用风控防线 (单标的仓位上限、硬止损、账户回撤熔断)
│   └── storage.py            # SQLite 数据持久化 (支持多数据库隔离)
│
├── markets/                  # 【市场适配器层】隔离具体市场的交易规则与行情源
│   ├── ashare/               # A 股 / ETF 适配器
│   │   ├── config.py         # 20,000元初始本金、T+1、100股整手、免印花税/过户费、ETF标的池
│   │   ├── broker.py         # AshareBroker: 严格执行 T+1 持仓锁定与整手申报撮合
│   │   └── data_feed.py      # AshareDataFeed: 腾讯金融极速行情 + AkShare日K
│   └── crypto/               # 币安 (Binance) 加密货币适配器
│       ├── config.py         # 5,000 USDT初始本金、7x24 T+0、小数位精度、Maker/Taker费率
│       ├── broker.py         # CryptoBroker: T+0 买入即时可用、浮点数撮合、USDT计价
│       └── data_feed.py      # CryptoDataFeed: 币安 REST API + HMAC-SHA256 签名 + 代理支持
│
├── strategies/               # 【量化算法策略池】
│   ├── base.py               # 策略抽象基类 (BaseStrategy, Signal)
│   ├── common/               # 跨市场通用策略 (一套代码两边复用)
│   │   ├── grid_trading.py   # 自适应网格套利策略 (支持 ETF 整手与 BTC/USDT 浮点小数)
│   │   └── dual_ma_trend.py  # EMA 趋势突破策略 + ATR 动态追踪止损
│   ├── ashare/               # A 股特有策略
│   │   └── momentum_rotation.py # 核心宽基/行业 ETF 动量轮动策略 (Gary Antonacci 双动量)
│   └── crypto/               # 币圈特有策略
│       └── bollinger_breakout.py# 布林带通道波动率突破策略 (适配 7x24 高波动率)
│
├── engines/                  # 【运行引擎】
│   ├── backtest_engine.py    # 跨市场事件驱动回测引擎 (年化、夏普、最大回撤、胜率并出图)
│   └── paper_engine.py       # 跨市场模拟盘引擎 (自动判断开盘时段、信号撮合、数据落盘)
│
├── main.py                   # 多市场交互式主控台 (支持按键一键切换市场)
├── run_backtest.py           # 命令行回测启动脚本 (支持 --market ashare 或 --market crypto)
├── run_paper_trade.py        # 命令行实盘模拟脚本 (支持 --market ashare 或 --market crypto)
└── data/                     # 历史数据、数据库与图表存储 (按子目录隔离)
    ├── ashare/               # A 股数据库与 K 线缓存
    └── crypto/               # 加密货币数据库与 K 线缓存
```

---

## 二、 市场特性对比矩阵

| 特性维度 | A 股 / 场内 ETF 子系统 | 币安 (Binance) 加密货币子系统 |
| :--- | :--- | :--- |
| **基础货币** | 人民币 (CNY)，默认本金 20,000 元 | 泰达币 (USDT)，默认本金 5,000 USDT |
| **交易时间** | 工作日 9:30-11:30, 13:00-15:00 | **7 × 24 小时全年无休** |
| **交收制度** | **T+1**（当日买入被锁定，次日可卖） | **T+0**（买入立即可以卖出） |
| **下单精度** | **整手限制**（必须是 100 股/份的整数倍） | **浮点小数**（如 0.0001 BTC） |
| **税费结构** | 佣金万 2.5、卖出印花税千 0.5 (ETF免征)、过户费十万分之一 | Maker 0.1%，Taker 0.1% |
| **数据源** | 腾讯金融实时行情 + AkShare 历史 K 线 | 币安官方 REST API (`/api/v3/klines`) |

---

## 三、 快速使用指南

### 1. 激活 Python 环境
```powershell
cd d:\Quant
.\.venv\Scripts\Activate.ps1
```

### 2. 配置币安 API 凭证 (可选代理)
在项目根目录编辑 `.env` 文件：
```ini
BINANCE_API_KEY=your_key_here
BINANCE_SECRET_KEY=your_secret_here
# 若国内直连网络受限，可配置本地科学上网代理端口
BINANCE_PROXY=http://127.0.0.1:7890
```

### 3. 启动交互式综合控制台
```powershell
python main.py
```
* 按 `[M]` 可在 **【A 股 / ETF 量化子系统】** 与 **【币安加密货币量化子系统】** 之间自由切换；
* 切换后，查看账户、回测策略、实盘模拟均自动路由至当前市场。

### 4. 命令行快捷回测

* **A 股 ETF 动量轮动策略回测**：
  ```powershell
  python run_backtest.py --market ashare --strategy rotation --start 20230101
  ```
* **币安 BTC/USDT 动态网格策略回测**：
  ```powershell
  python run_backtest.py --market crypto --strategy grid --symbol BTCUSDT --start 20240101
  ```
* **币安 ETH/USDT 布林带突破策略回测**：
  ```powershell
  python run_backtest.py --market crypto --strategy bollinger --symbol ETHUSDT --start 20240101
  ```

### 5. 命令行快捷模拟实盘

* **A 股单次巡检撮合**：
  ```powershell
  python run_paper_trade.py --market ashare --strategy rotation
  ```
* **币安加密货币单次巡检撮合**：
  ```powershell
  python run_paper_trade.py --market crypto --strategy grid --symbol BTCUSDT
  ```
* **币安加密货币 7x24 循环监控盯盘**：
  ```powershell
  python run_paper_trade.py --market crypto --strategy grid --symbol BTCUSDT --loop --interval 60
  ```
