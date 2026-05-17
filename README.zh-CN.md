# Trade Review · 个人交易复盘工具

> 本机运行的 AI 交易教练，覆盖 A 股 / 港股 / 美股，支持 Claude OAuth 或 DeepSeek API Key

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab.svg)](https://www.python.org/)
[![English](https://img.shields.io/badge/-English-blue.svg)](README.md)

把每一笔交易变成一次结构化复盘：成交后立刻给**盘中闪评**、收盘后给**每日复盘**、每周一张**心态雷达图**、还有可检索的**交易日志**。覆盖 A 股、港股、美股。

完全在你自己的电脑上跑，AI 引擎可以走两条路：复用你**本地的 Claude Code OAuth 登录**，
也可以填入 **DeepSeek API Key** 通过 OpenAI-compatible 接口调用。

> ⚠️ **风险提示**：这是个人复盘工具，不是投资建议。AI 在价格、日期、基本面上都可能出错，做决策前请自行核对。

---

## 截图

| 仪表盘 | 盘中闪评 | 周度心态 |
|---|---|---|
| _稍后补图_ | _稍后补图_ | _稍后补图_ |

---

## 功能

- 🔥 **盘中闪评**（≤10 秒）—— 输入一笔交易，得到 时机/心态/技术 三维 JSON 评分，加三个未来剧本（带概率、触发条件、对应操作）
- 📋 **每日复盘** —— 流式生成每只持仓的明日操作建议、技术位、基本面要点、风险点
- 🧭 **周度心态雷达** —— 基于你的历史标签算 6 维分数：纪律 / 情绪稳定 / 耐心 / 独立判断 / 风控执行 / 学习力
- 🏷️ **规则化行为标签** —— 内置 7 类检测器：追涨、杀跌、报复性交易、频繁交易、逆势、拖单、过早止盈
- 📊 **多市场行情** —— A 股 [akshare](https://github.com/akfamily/akshare)，港美股 [yfinance](https://github.com/ranaroussi/yfinance)，自动兜底
- 🤖 **多 AI 引擎** —— Claude Sonnet 4.6 走本地 Claude Code OAuth，DeepSeek 走 API Key
- 🔒 **单用户鉴权** —— 自动生成 24 字符访问 Token；可选 [Tailscale](https://tailscale.com/) 私网，让手机/iPad 也能用

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│       React 19 + TypeScript + Tailwind  （单端口 SPA）        │
│       仪表盘 · 闪评 · 复盘 · 心态 · 日志                       │
└────────────────────────┬─────────────────────────────────────┘
                         │  REST + Server-Sent Events
                         ▼
┌──────────────────────────────────────────────────────────────┐
│   FastAPI                                                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Flash · Daily · Chat · Mindset · Trades · Positions   │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │ 心态规则引擎 │  │   行情聚合层      │  │   AI 引擎层     │   │
│  │  （7 标签）  │  │ akshare/yfinance │  │（持久会话预热）  │   │
│  │             │  │   + 可选 iFinD   │  │                 │   │
│  └─────────────┘  └──────────────────┘  └────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    SQLite                              │  │
│  │  trades · positions · reviews · mindset_tags · weekly  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 0. 前置依赖
#    - macOS / Linux
#    - Python 3.11+
#    - Node.js 20+
#    - AI 引擎：
#      Claude 模式：npm i -g @anthropic-ai/claude-code && claude
#      DeepSeek 模式：在 .env 填 DEEPSEEK_API_KEY

# 1. 克隆 + 装依赖
git clone https://github.com/hjjbh1314/trade-review
cd trade-review
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2.（可选）个性化
cp .env.example .env
# 编辑 .env，比如把 TR_USER_NAME 改成你的昵称，或切换 TR_AI_ENGINE

# 3. 启动
./start.sh
# → 终端会打印一行带 token 的访问 URL
```

第一次启动会做：
1. 生成 `.tr_token`（权限 600，已加入 .gitignore）
2. `npm install` + 构建前端到 `frontend/dist/`
3. 检查所选 AI 引擎配置
4. 打印形如 `http://127.0.0.1:8090/#token=xxx` 的 URL；浏览器打开后 Token 会存到 localStorage 7 天，之后直接访问根 URL 即可

### 多设备模式（Tailscale）

想在手机/iPad 上看，又不想被同 Wi-Fi 别人扫到端口：

```bash
brew install --cask tailscale         # 一次性
./start.sh --tailscale
```

服务只绑到你的 Tailscale 虚拟网卡。同一 Tailscale 账号下的设备能用，公共 Wi-Fi 同子网的人完全看不见你的端口。

> ⚠️ 旧的 `--lan` 模式已移除（设计选择）。在公共 Wi-Fi 绑 0.0.0.0 等于把持仓暴露给所有同子网用户，请改用 Tailscale。

---

## 配置项

全部通过环境变量，复制 `.env.example` 到 `.env` 编辑：

| 变量 | 默认 | 作用 |
|---|---|---|
| `TR_USER_NAME` | 空 | AI 教练对你的称呼，不填用 "the trader" |
| `VITE_USER_NAME` | 同上 | 前端顶栏显示的名字（构建时注入） |
| `TR_AI_ENGINE` | `claude` | AI 引擎。`claude` 走本地 Claude Code OAuth，`deepseek` 走 API Key |
| `DEEPSEEK_API_KEY` | 空 | `TR_AI_ENGINE=deepseek` 时必填 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型名；需要推理模型可改 `deepseek-reasoner` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible chat completions base URL |
| `IFIND_AUTH_TOKEN` | 空 | iFinD 增强（A 股自然语言摘要），不填也能用 |

`TR_ACCESS_TOKEN` 由 `start.sh` 自动生成存到 `.tr_token`。要轮换 Token，删掉 `.tr_token` 重启即可。

---

## 目录结构

```
trade_review/
├── backend/                       FastAPI 后端
│   ├── main.py                    入口（lifespan / CORS / 路由挂载）
│   ├── auth.py                    Token 中间件（header / cookie / query）
│   ├── api/                       路由
│   │   ├── flash.py               POST /api/flash/review/stream  (SSE)
│   │   ├── daily.py               POST /api/daily/review/stream  (SSE)
│   │   ├── chat.py                POST /api/chat/message/stream  (SSE)
│   │   ├── mindset.py             GET  /api/mindset/weekly
│   │   ├── positions.py           CRUD + /with-quotes
│   │   ├── market.py              GET  /api/market/kline
│   │   └── trades.py              CRUD + /journal
│   ├── ai/                        AI 引擎适配
│   │   ├── claude_engine.py       持久 ClaudeSDKClient
│   │   ├── deepseek_engine.py     OpenAI-compatible DeepSeek 适配
│   │   └── prompts.py             闪评/复盘 prompt 模板
│   ├── market/
│   │   ├── aggregator.py          akshare + yfinance 聚合 + JSON 安全
│   │   └── ifind_adapter.py       可选增强
│   ├── mindset/
│   │   ├── rule_engine.py         7 类标签检测
│   │   └── weekly.py              6 维雷达
│   └── db/{schema.sql, repo.py}   SQLite
├── frontend/                      Vite + React 19 + Tailwind 3
├── data/                          （gitignored）你的 SQLite 数据库
├── start.sh                       一键启动
├── DESIGN.md                      设计文档
└── README.md / README.zh-CN.md
```

---

## API 文档

启动后访问 `http://127.0.0.1:8090/docs` 看 OpenAPI 自动生成的交互式文档。

主要端点：

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/api/flash/review/stream` | 盘中闪评 SSE 流式输出 |
| `POST` | `/api/daily/review/stream` | 每日持仓复盘 SSE |
| `POST` | `/api/chat/message/stream` | 针对持仓的自由问答 |
| `GET`  | `/api/mindset/weekly?week=2026-W17` | 周度雷达 + 典型错误 + 寄语 |
| `GET`  | `/api/positions/with-quotes` | 持仓 + 实时现价 + 浮盈 |
| `GET`  | `/api/market/kline?symbol=600519&market=A&period=daily&limit=120` | K 线 + MA5/MA20 |

所有 `/api/*`（除 `/api/health` 和 `/api/auth-status` 外）都需要 Token，三种方式之一：

- Header：`X-TR-Token: <token>`
- Cookie：`tr_token=<token>`
- Query：`?token=<token>`

---

## 技术栈

- **后端**：Python 3.11+，FastAPI，SQLite，asyncio
- **AI**：可插拔引擎；Claude Sonnet 4.6 via [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk-python) 走 Claude Code OAuth，DeepSeek 走 OpenAI-compatible API
- **行情**：[akshare](https://github.com/akfamily/akshare)、[yfinance](https://github.com/ranaroussi/yfinance)、可选 iFinD MCP
- **前端**：React 19、TypeScript、TailwindCSS、Vite、[lightweight-charts](https://github.com/tradingview/lightweight-charts)
- **网络**：可选 [Tailscale](https://tailscale.com) 私网

---

## Roadmap

- [ ] 行业 / 大盘聚合写入每日复盘
- [ ] T+1/T+3/T+5 持仓后续走势回测（schema 已留好 `trade_outcomes` 表）
- [x] 多 AI 引擎：Claude OAuth / DeepSeek API
- [ ] 更多引擎：Codex / OpenAI-compatible presets
- [ ] 可选 Postgres 后端，支持多用户
- [ ] Demo 截图 + 视频演示

---

## 贡献

欢迎 Issue / PR：

1. 非小修建议先开 Issue 对齐范围
2. PR 聚焦：一次只修一个 bug 或加一个功能
3. 提交前在本地跑 `./start.sh` 走一遍主要流程

---

## License

[MIT](LICENSE)

---

## 致谢

- [Anthropic Claude](https://www.anthropic.com/) 提供模型和开放的 Agent SDK
- [akshare](https://github.com/akfamily/akshare) 和 [yfinance](https://github.com/ranaroussi/yfinance) 提供免费行情
- [TradingView lightweight-charts](https://github.com/tradingview/lightweight-charts) 提供 K 线组件
