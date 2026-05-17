# Trade Review · 系统设计文档

> 版本：v1.0 · 2026-04-24
> 用途：个人多市场交易复盘工具（A股 + 港股 + 美股）

---

## 1. 产品定位

一个**个人向**的交易复盘与决策辅助系统，覆盖两个核心场景：

| 场景 | 触发时机 | 交付物 |
|---|---|---|
| **盘中闪评** | 刚做完一笔交易，立刻问 | 30 秒内给出 时机/心态/技术 三维评分 + 证据链 + 后续剧本 |
| **每日复盘** | 收盘后或睡前 | 每只持仓的明日操作建议 + 技术位 + 基本面 + 风险 |

辅以两个长期价值模块：

- **周度心态画像** —— 每周一生成，雷达图 + 标签云 + 典型错误
- **交易日志** —— 结构化记录，关联复盘、标签、后续走势

---

## 2. 技术栈

| 层 | 技术 | 理由 |
|---|---|---|
| 前端 | **React 18 + TypeScript + TailwindCSS + Vite** | 类型安全、主流、与 mockup 无缝衔接 |
| 图表 | **lightweight-charts**（TradingView 开源） | 免费商用、性能强、K 线标配 |
| 状态 | **Zustand**（轻量 store）+ React Query（服务端状态） | 比 Redux 轻 |
| 后端 | **FastAPI（Python 3.11+）** | 异步、自动 OpenAPI 文档、SSE 流式 |
| AI 引擎 | **Claude Agent SDK**（主，OAuth）+ Codex（备） | 走 Max 订阅零额外费用；适配器模式可切换 |
| 数据库 | **SQLite**（初期）→ 可平滑迁移 Postgres | 单机零运维 |
| 数据源 | iFinD MCP（A股，已有）· akshare（A股兜底）· yfinance（港美股）· WebSearch（新闻基本面） | 多源兜底 |
| 技术指标 | **pandas-ta** 或 **TA-Lib** | 纯 Python，装一个就够用 |
| 部署 | 本机 `uvicorn` + `vite build` → 单机使用 | 个人用无需 Docker |

---

## 3. 系统架构

```
┌───────────────────────────────────────────────────────────────┐
│                    浏览器 (React SPA)                          │
│   Dashboard | Flash | Daily | Mindset | Journal               │
└────────┬──────────────────────────────────────────────┬───────┘
         │ REST + SSE                                    │ WS (可选)
         ▼                                               ▼
┌────────────────────────────────────────────────────────────┐
│                 FastAPI 后端 (本机 8080)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Review API  │  │ Market API   │  │ Mindset API        │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────┘ │
│         │                │                     │           │
│  ┌──────▼──────────────────▼─────────────────────▼────────┐ │
│  │         Service Layer（业务逻辑）                       │ │
│  │  AIEngine · MindsetRuleEngine · MarketDataAggregator   │ │
│  └──────┬──────────────────┬─────────────────────┬────────┘ │
│         │                  │                     │          │
│  ┌──────▼──────┐  ┌────────▼──────┐  ┌───────────▼────────┐ │
│  │ Claude      │  │ 多源行情适配层  │  │ SQLite            │ │
│  │ Agent SDK   │  │ iFinD/akshare/│  │ trades,positions, │ │
│  │ (或 Codex)  │  │ yfinance      │  │ reviews, mindset  │ │
│  └─────────────┘  └───────────────┘  └───────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

**数据流（盘中闪评）**：

```
用户录入交易 → POST /api/flash/review
  ↓
后端拉多源行情（分时 + 日K + 大盘）
  ↓
MindsetRuleEngine 结构化打标签（追涨/杀跌/过早止盈…）
  ↓
AIEngine（Claude）基于标签 + 行情 → 生成评分 + 证据链 + 剧本
  ↓
SSE 流式返回前端，同时落库
```

---

## 4. 数据库 Schema

```sql
-- 交易流水
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,                 -- 600519 / 00700 / AAPL
    market          TEXT NOT NULL CHECK (market IN ('A', 'HK', 'US')),
    name            TEXT,                          -- 贵州茅台
    action          TEXT NOT NULL CHECK (action IN ('buy', 'sell')),
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    trade_time      DATETIME NOT NULL,             -- 含时分
    reason          TEXT,                          -- 用户填的理由
    mood            TEXT,                          -- 冷静/兴奋/犹豫/恐惧/贪婪/报复
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 持仓快照（每次操作后更新）
CREATE TABLE positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    market          TEXT NOT NULL,
    name            TEXT,
    quantity        INTEGER NOT NULL,
    cost_price      REAL NOT NULL,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, market)
);

-- 复盘记录（盘中闪评 + 每日复盘共用）
CREATE TABLE reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type     TEXT NOT NULL CHECK (review_type IN ('flash', 'daily')),
    trade_id        INTEGER REFERENCES trades(id),  -- flash 时指向具体交易
    review_date     DATE NOT NULL,
    scores_json     TEXT,       -- {"timing":68, "mindset":55, "technical":78}
    tags_json       TEXT,       -- ["追涨","趋势跟随"]
    report_md       TEXT NOT NULL,    -- Claude 生成的完整 markdown 报告
    scenarios_json  TEXT,       -- 后续剧本（乐观/中性/悲观）
    lesson          TEXT,       -- 一句话教训
    ai_engine       TEXT,       -- "claude-sonnet-4-6" / "codex"
    ai_latency_ms   INTEGER,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 心态标签（规则层产出，用于画像聚合）
CREATE TABLE mindset_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id),
    tag             TEXT NOT NULL,                    -- 追涨/杀跌/过早止盈/拖单/报复/逆势/频繁
    severity        TEXT CHECK (severity IN ('light', 'medium', 'heavy')),
    evidence_json   TEXT,                             -- 触发证据
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 周度心态画像
CREATE TABLE weekly_mindset (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year_week       TEXT NOT NULL UNIQUE,             -- "2026-W17"
    week_start      DATE NOT NULL,
    week_end        DATE NOT NULL,
    radar_json      TEXT,                             -- 6 维评分
    tags_summary    TEXT,                             -- {"追涨":3,"杀跌":1,...}
    top_errors_json TEXT,                             -- 本周 3 个典型错误
    ai_message      TEXT,                             -- AI 寄语
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 后续走势跟踪（事后自动回填）
CREATE TABLE trade_outcomes (
    trade_id        INTEGER PRIMARY KEY REFERENCES trades(id),
    t_plus_1_pct    REAL,         -- T+1 涨跌幅
    t_plus_3_pct    REAL,
    t_plus_5_pct    REAL,
    hindsight_tag   TEXT,          -- "过早止盈" / "杀跌反弹" / "持有正确"
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_symbol_time ON trades(symbol, trade_time DESC);
CREATE INDEX idx_reviews_date ON reviews(review_date DESC);
CREATE INDEX idx_mindset_tags_trade ON mindset_tags(trade_id);
```

---

## 5. API 定义

> Base URL: `http://127.0.0.1:8080/api`

### 5.1 交易 & 持仓

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/trades` | 录入一笔交易，自动打心态标签 |
| `GET`  | `/trades?symbol=600519&limit=50` | 查询交易流水 |
| `GET`  | `/positions` | 当前持仓列表（含实时盈亏） |
| `PUT`  | `/positions/{symbol}` | 更新持仓（编辑成本/数量） |
| `DELETE` | `/positions/{symbol}` | 删除持仓 |

### 5.2 复盘

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/flash/review` | 盘中闪评，SSE 流式返回 |
| `POST` | `/daily/review` | 每日复盘，SSE 流式返回 |
| `GET`  | `/reviews/{id}` | 获取单个复盘详情 |
| `GET`  | `/reviews?date=2026-04-24` | 按日期查询 |

### 5.3 市场数据

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/market/quote?symbol=600519&market=A` | 实时行情 + 技术指标 |
| `GET` | `/market/kline?symbol=600519&period=daily&limit=120` | K 线数据 |
| `GET` | `/market/index` | 大盘状态（上证/恒生/纳指/北向） |

### 5.4 心态画像

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET`  | `/mindset/weekly?week=2026-W17` | 周度画像 |
| `POST` | `/mindset/weekly/regenerate` | 手动重算本周 |

### 5.5 对话（侧边栏 AI 聊天）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/chat/message` | 自由追问，SSE 流式；Claude 可调 tool（行情/新闻）|

### SSE 事件格式

```
event: status
data: {"phase": "fetching_market"}

event: chunk
data: {"text": "加仓时点..."}

event: tags
data: {"tags": ["追涨","趋势跟随"], "scores": {"timing":68,...}}

event: done
data: {"review_id": 123, "saved_path": "..."}
```

---

## 6. 心态诊断规则层

**核心思想：规则层先打"硬标签"，AI 再做"软解读"。** 规则是可解释的证据，AI 不会胡编。

### 6.1 标签定义（7 类）

| 标签 | 触发条件（A 股 / 港美股同框架，阈值可配） |
|---|---|
| **追涨** | 买入价 ≥ 开盘价 × 1.02 **且** 买入前 30 分钟涨幅 ≥ 1.5% **且** 日涨幅 ≥ 2% |
| **杀跌** | 卖出价 ≤ 开盘价 × 0.98 **且** 卖出前 30 分钟跌幅 ≥ 1.5% **且** 日跌幅 ≥ 2% |
| **过早止盈** | （事后 T+1 回填）卖出后次日继续涨 ≥ 2% |
| **拖单** | 浮亏 ≥ 5% 当日未止损，且技术面已破位（收盘跌破 MA20） |
| **报复性交易** | 前一笔亏损后 2 小时内再开新仓（同市场） |
| **逆势** | 大盘跌 ≥ 1% **且** 板块跌 ≥ 1.5% 时加仓 |
| **频繁** | 单日交易笔数 ≥ 4（不含 T+0 对冲） |

### 6.2 严重程度分级

```python
severity = "light" | "medium" | "heavy"
# 例：追涨
#   light  : 买入前 30min 涨幅 1.5-2.5%
#   medium : 2.5-4%
#   heavy  : >4%（情绪尾端）
```

### 6.3 规则引擎伪代码

```python
class MindsetRuleEngine:
    def tag_trade(self, trade: Trade, market: MarketSnapshot) -> list[Tag]:
        tags = []

        if trade.action == 'buy':
            if self._is_chase(trade, market):
                tags.append(Tag('追涨', severity=self._chase_severity(trade, market),
                                evidence=self._chase_evidence(trade, market)))
            if self._is_counter_trend(trade, market):
                tags.append(Tag('逆势', ...))

        if trade.action == 'sell':
            if self._is_panic_sell(trade, market):
                tags.append(Tag('杀跌', ...))

        if self._is_revenge(trade):
            tags.append(Tag('报复性交易', ...))

        if self._is_drag(trade):
            tags.append(Tag('拖单', ...))

        return tags
```

### 6.4 标签 → AI 提示

规则层的标签作为**系统提示的一部分**传给 Claude，Claude 基于标签做解读和建议，而不是从零判断：

```
【机器识别】
本笔已自动识别：[轻度追涨, 趋势跟随]
证据：
  - 买入价 ¥1680 vs 开盘价 ¥1655（+1.51%）
  - 买入前 30min 涨幅 +0.9%，放量 1.8x

请基于以上事实，输出 3 段结构化诊断...
```

---

## 7. AI 引擎适配层

### 7.1 双引擎可插拔

```python
# ai/base.py
class AIEngine(Protocol):
    async def review(self, prompt: str, tools: list[Tool] = None) -> AsyncIterator[str]:
        ...

# ai/claude_engine.py
class ClaudeEngine:
    def __init__(self):
        from claude_agent_sdk import ClaudeSDKClient
        self.client = ClaudeSDKClient()  # OAuth 自动读 ~/.claude/.credentials.json

    async def review(self, prompt, tools=None):
        async for chunk in self.client.query(prompt, allowed_tools=tools):
            yield chunk

# ai/codex_engine.py
class CodexEngine:
    # 通过 codex CLI subprocess 或 OpenAI SDK 实现
    ...

# 选择器
def get_ai_engine() -> AIEngine:
    engine = os.environ.get("TR_AI_ENGINE", "claude")
    return ClaudeEngine() if engine == "claude" else CodexEngine()
```

### 7.2 工具注入（Claude tool use）

给 Claude 挂以下工具，让它自主选择调用：

| 工具名 | 作用 | 实现 |
|---|---|---|
| `get_stock_quote` | 查实时行情 | 包装 iFinD MCP / akshare / yfinance |
| `get_kline` | 查指定周期 K 线 | 同上 |
| `get_news` | 查最新新闻 | iFinD news MCP + WebSearch 双源 |
| `get_fundamentals` | 查基本面（财报、估值） | iFinD + WebSearch |
| `search_peer_companies` | 查同行业标的 | iFinD stock search |

Claude 会在生成报告时主动决定"需要查一下最近新闻"，自动调用工具，比写死在 Prompt 里更灵活。

### 7.3 Prompt 模板（盘中闪评）

```python
FLASH_PROMPT = """你是一位风格直接的交易教练，服务对象是 {{TR_USER_NAME}}。
对他的这笔交易输出结构化闪评，语言中文，必须基于提供的事实，不允许编造。

【交易】
{symbol} {action} {quantity} 股 @ {price}，时间 {time}
市场：{market}（A/HK/US）
理由：{reason}
当前心态：{mood}

【机器识别标签】
{rule_tags_with_evidence}

【市场快照】
分时摘要：{intraday_summary}
日K摘要：{daily_k_summary}
大盘：{index_status}
板块：{sector_status}

【输出格式 - 严格 JSON】
{
  "scores": {"timing": 0-100, "mindset": 0-100, "technical": 0-100},
  "mindset_tags": [...],
  "mindset_reasoning": "证据链文本",
  "technical_reading": "K 线和指标解读",
  "scenarios": [
    {"name": "乐观", "probability": 40, "trigger": "...", "action": "..."},
    {"name": "中性", "probability": 45, "...": "..."},
    {"name": "悲观", "probability": 15, "...": "..."}
  ],
  "one_line_lesson": "一句话"
}
"""
```

---

## 8. 行情数据适配层

```python
# market/aggregator.py
class MarketDataAggregator:
    async def get_quote(self, symbol: str, market: str) -> Quote:
        if market == 'A':
            return await self._a_share_quote(symbol)  # iFinD → akshare 兜底
        elif market == 'HK':
            return await self._hk_quote(symbol)       # yfinance（0700.HK）
        elif market == 'US':
            return await self._us_quote(symbol)       # yfinance

    async def get_kline(self, symbol, market, period='daily', limit=120):
        ...

    async def compute_indicators(self, kline: pd.DataFrame) -> Indicators:
        # pandas-ta 算 MA / MACD / RSI / BOLL / ATR
        ...
```

**代码格式约定**：

| 市场 | 用户输入 | 内部 yfinance 格式 |
|---|---|---|
| A 股 | `600519` | （不用，走 iFinD/akshare） |
| 港股 | `00700` | `0700.HK` |
| 美股 | `AAPL` | `AAPL` |

---

## 9. 目录结构

```
trade_review/
├── DESIGN.md                  # 本文档
├── mockup/
│   └── index.html             # UI mockup
├── backend/
│   ├── main.py                # FastAPI app
│   ├── db/
│   │   ├── schema.sql
│   │   └── repo.py
│   ├── ai/
│   │   ├── base.py            # AIEngine protocol
│   │   ├── claude_engine.py
│   │   ├── codex_engine.py
│   │   └── prompts.py
│   ├── market/
│   │   ├── aggregator.py
│   │   ├── ifind_adapter.py   # 保留现有 ifind_client.py
│   │   ├── akshare_adapter.py
│   │   └── yfinance_adapter.py
│   ├── mindset/
│   │   ├── rule_engine.py
│   │   └── weekly.py          # 周度画像聚合
│   ├── api/
│   │   ├── trades.py
│   │   ├── reviews.py
│   │   ├── market.py
│   │   ├── mindset.py
│   │   └── chat.py
│   └── settings.py
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Flash.tsx
│   │   │   ├── Daily.tsx
│   │   │   ├── Mindset.tsx
│   │   │   └── Journal.tsx
│   │   ├── components/
│   │   │   ├── KLineChart.tsx
│   │   │   ├── ChatPanel.tsx  # 可拖拽对话窗
│   │   │   └── MindsetRadar.tsx
│   │   ├── api.ts
│   │   └── store.ts           # Zustand
│   ├── index.html
│   └── vite.config.ts
├── data/
│   └── trade_review.db        # SQLite
├── _legacy/                   # 现有 main.py / web_server.py 暂存，迁移后清理
└── .env
```

---

## 10. 分阶段实施计划

| 阶段 | 内容 | 预计工作量 |
|---|---|---|
| **P0 · MVP 骨架** | 数据库 schema · FastAPI 框架 · Claude Agent SDK 接入 · 盘中闪评端到端（后端 + 简易前端） | 1-2 晚 |
| **P1 · 三市场数据** | yfinance 港美股 · 技术指标 · iFinD 对接新版本 · MindsetRuleEngine 完整实现 | 2 晚 |
| **P2 · 前端完整** | React + TailwindCSS 按 mockup 实现 5 个视图 · lightweight-charts · 可拖拽对话窗 | 2-3 晚 |
| **P3 · 每日复盘 + Claude tools** | 每日复盘多卡片 · Claude tool use（行情/新闻）· SSE 流式 | 1-2 晚 |
| **P4 · 周度心态 + 事后回填** | weekly 聚合任务 · trade_outcomes T+1/T+3/T+5 回填 · 雷达图 | 1 晚 |
| **P5 · 抛光** | 导出 PDF · 截图上传 · 键盘快捷键 · 错误处理完善 | 按需 |

**总计：约 7-10 个晚上**（全职 2-3 天）。

---

## 11. 风险与 Plan B

| 风险 | 应对 |
|---|---|
| Claude OAuth 某天不可用 | 一行配置 `TR_AI_ENGINE=codex` 切到 Codex |
| iFinD 密钥过期 / 限额 | akshare + yfinance 兜底，A 股不会断 |
| yfinance 被墙 | 切 Alpha Vantage 或自建代理 |
| 规则误判（例如追涨阈值太严） | 阈值全写在 `settings.py`，可按历史交易回测调参 |
| SQLite 性能（交易数据膨胀） | 单表千级无压力；超过万级再迁 Postgres |

---

## 12. 安全 & 隐私

- 所有数据**仅本机**（127.0.0.1 绑定，不对外开放）
- Claude OAuth token 由 Claude Code 本身管理，本应用只调 SDK，不读 token
- 无第三方统计、无外发、无云同步
- 敏感数据（持仓金额）可选本地加密（后续加，P5）

---

## 13. 下一步

你点头后：

1. **P0 立即可写**：建目录、迁数据库、接 Claude Agent SDK、盘中闪评打通。
2. **现有代码处理**：`main.py` / `web_server.py` / `frontend.py` 暂移到 `_legacy/`，等新版跑通后再删（不会立刻删任何东西）。

需要我先做两件事之一：

- **a.** 直接开工 P0（我搭骨架、写 schema、接 Claude SDK，跑通一笔闪评给你看）
- **b.** 你先审这份 DESIGN.md，提修改意见再开工
