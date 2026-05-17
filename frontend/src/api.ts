/**
 * API 客户端。流式闪评用 fetch + ReadableStream 解析 SSE。
 */
export type Market = 'A' | 'HK' | 'US';
export type Action = 'buy' | 'sell';

// ─── Token 管理 ──────────────────────────────────────────────
const TOKEN_KEY = 'tr-access-token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** 统一的 fetch，自动注入 X-TR-Token header；401 时抛 UnauthorizedError */
export class UnauthorizedError extends Error {
  constructor() { super('未授权'); this.name = 'UnauthorizedError'; }
}

export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token) headers.set('X-TR-Token', token);
  const r = await fetch(input, { ...init, headers });
  if (r.status === 401) {
    clearToken();
    throw new UnauthorizedError();
  }
  return r;
}

export async function checkAuthStatus(): Promise<{ required: boolean }> {
  const r = await fetch('/api/auth-status');
  if (!r.ok) return { required: false };
  return r.json();
}

export async function verifyToken(token: string): Promise<boolean> {
  // 直接用 fetch 绕开 authFetch 的自动注入（authFetch 会覆盖 header）
  const r = await fetch('/api/positions', { headers: { 'X-TR-Token': token } });
  return r.status !== 401;
}


export interface TradeInput {
  symbol: string;
  market: Market;
  name?: string;
  action: Action;
  price: number;
  quantity: number;
  trade_time: string;      // "2026-04-24 14:20:00"
  reason?: string;
  mood?: string;
}

export interface Snapshot {
  market: string;
  open?: number;
  last?: number;
  daily_change_pct?: number;
  pre30_change_pct?: number;
  ma5?: number;
  ma20?: number;
  macd_note?: string;
  rsi?: number;
  index_note?: string;
  sector_note?: string;
  error?: string;
}

export interface RuleTag {
  tag: string;
  severity: 'light' | 'medium' | 'heavy';
  evidence: Record<string, unknown>;
}

export interface Scores {
  timing: number;
  mindset: number;
  technical: number;
}

export interface Scenario {
  name: string;
  probability: number;
  trigger: string;
  action: string;
}

export interface ParsedReview {
  scores?: Scores;
  mindset_tags?: string[];
  mindset_reasoning?: string;
  technical_reading?: string;
  scenarios?: Scenario[];
  one_line_lesson?: string;
}

export type SSEEvent =
  | { type: 'status'; data: { phase: string } }
  | { type: 'snapshot'; data: Snapshot }
  | { type: 'tags'; data: RuleTag[] }
  | { type: 'chunk'; data: { text: string } }
  | { type: 'parsed'; data: ParsedReview }
  | { type: 'done'; data: { trade_id: number; review_id: number; latency_ms: number; engine: string; parse_error?: string | null } }
  | { type: 'error'; data: { message: string; type: string } };

export async function* streamFlashReview(
  input: TradeInput,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const resp = await authFetch('/api/flash/review/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
    body: JSON.stringify(input),
    signal,
  });
  if (!resp.body) throw new Error('响应无 body');
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE 按双换行分块
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const part of parts) {
      const lines = part.split('\n');
      let ev = '';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data = line.slice(5).trim();
      }
      if (!ev || !data) continue;
      try {
        yield { type: ev as SSEEvent['type'], data: JSON.parse(data) } as SSEEvent;
      } catch {
        // skip malformed
      }
    }
  }
}

export async function health(): Promise<boolean> {
  try {
    const r = await fetch('/api/health');
    return r.ok;
  } catch {
    return false;
  }
}

// ─── Positions ────────────────────────────────────────────────────
export interface Position {
  id: number;
  symbol: string;
  market: Market;
  name?: string | null;
  quantity: number;
  cost_price: number;
  updated_at?: string;
  last_price?: number | null;
  daily_change_pct?: number | null;
  market_value?: number;
  pnl?: number;
  pnl_pct?: number;
}

export interface MarketSummary {
  market_value: number;
  pnl: number;
  count: number;
}

export interface PositionsWithQuotes {
  ok: boolean;
  items: Position[];
  summary: Record<string, MarketSummary>;
}

export async function fetchPositionsWithQuotes(): Promise<PositionsWithQuotes> {
  const r = await authFetch('/api/positions/with-quotes');
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function createPosition(p: Omit<Position, 'id' | 'updated_at'>): Promise<void> {
  const r = await authFetch('/api/positions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: p.symbol, market: p.market, name: p.name,
      quantity: p.quantity, cost_price: p.cost_price,
    }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export async function deletePosition(market: Market, symbol: string): Promise<void> {
  const r = await authFetch(`/api/positions/${market}/${symbol}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

// ─── Trades ───────────────────────────────────────────────────────
export interface TradeRecord extends TradeInput {
  id: number;
  created_at?: string;
}

export async function listTrades(symbol?: string, limit = 50): Promise<TradeRecord[]> {
  const qs = new URLSearchParams();
  if (symbol) qs.set('symbol', symbol);
  qs.set('limit', String(limit));
  const r = await authFetch(`/api/trades?${qs.toString()}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const d = await r.json();
  return d.items ?? [];
}

export interface JournalTag {
  tag: string;
  severity: 'light' | 'medium' | 'heavy';
  evidence_json?: string;
}
export interface JournalReview {
  id: number;
  scores_json?: string | null;
  tags_json?: string | null;
  lesson?: string | null;
}
export interface JournalItem extends TradeRecord {
  tags: JournalTag[];
  review?: JournalReview | null;
}

export async function fetchJournal(symbol?: string, tag?: string, limit = 200): Promise<JournalItem[]> {
  const qs = new URLSearchParams();
  if (symbol) qs.set('symbol', symbol);
  if (tag) qs.set('tag', tag);
  qs.set('limit', String(limit));
  const r = await authFetch(`/api/trades/journal?${qs.toString()}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const d = await r.json();
  return d.items ?? [];
}

// ─── Chat ─────────────────────────────────────────────────────────
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatFocus {
  symbol?: string;
  market?: Market;
  name?: string | null;
  cost_price?: number;
  quantity?: number;
}

export type ChatSSEEvent =
  | { type: 'status'; data: { phase: string } }
  | { type: 'chunk'; data: { text: string } }
  | { type: 'done'; data: { latency_ms: number; engine: string } }
  | { type: 'error'; data: { message: string; type?: string } };

// ─── Mindset ──────────────────────────────────────────────────────
export interface MindsetRadar {
  discipline: number;
  emotion: number;
  patience: number;
  autonomy: number;
  risk_ctrl: number;
  learning: number;
}

export interface MindsetError {
  trade_id: number;
  symbol: string;
  trade_time: string;
  tag: string;
  severity: string;
  evidence: Record<string, unknown>;
}

export interface WeeklyMindset {
  ok: boolean;
  year_week: string;
  week_start: string;
  week_end: string;
  trade_count: number;
  tag_counts: Record<string, number>;
  radar: MindsetRadar;
  top_errors: MindsetError[];
  ai_message?: string | null;
}

export async function fetchWeeklyMindset(week?: string, aiMessage = true): Promise<WeeklyMindset> {
  const qs = new URLSearchParams();
  if (week) qs.set('week', week);
  qs.set('ai_message', aiMessage ? 'true' : 'false');
  const r = await authFetch(`/api/mindset/weekly?${qs.toString()}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchAvailableWeeks(limit = 12): Promise<Array<{ year_week: string; start: string; end: string }>> {
  const r = await authFetch(`/api/mindset/weeks?limit=${limit}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const d = await r.json();
  return d.items ?? [];
}

export async function* streamChatMessage(
  messages: ChatMessage[],
  focus: ChatFocus | null,
  signal?: AbortSignal,
): AsyncGenerator<ChatSSEEvent> {
  const resp = await authFetch('/api/chat/message/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
    body: JSON.stringify({ messages, focus: focus ?? undefined }),
    signal,
  });
  if (!resp.body) throw new Error('响应无 body');
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const part of parts) {
      const lines = part.split('\n');
      let ev = '';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data = line.slice(5).trim();
      }
      if (!ev || !data) continue;
      try {
        yield { type: ev as ChatSSEEvent['type'], data: JSON.parse(data) } as ChatSSEEvent;
      } catch {
        // skip
      }
    }
  }
}

// ─── Market ───────────────────────────────────────────────────────
export interface KLineBar {
  time: string;          // 'YYYY-MM-DD'
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KLineResponse {
  ok: boolean;
  symbol: string;
  market: Market;
  period: 'daily' | 'weekly' | 'monthly';
  bars: KLineBar[];
  ma5: { time: string; value: number }[];
  ma20: { time: string; value: number }[];
}

export async function fetchKLine(
  symbol: string, market: Market,
  period: 'daily' | 'weekly' | 'monthly' = 'daily',
  limit = 120,
): Promise<KLineResponse> {
  const qs = new URLSearchParams({ symbol, market, period, limit: String(limit) });
  const r = await authFetch(`/api/market/kline?${qs.toString()}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ─── Daily Review ─────────────────────────────────────────────────
export interface DailyPositionAdvice {
  symbol: string;
  market: Market;
  name?: string | null;
  stage: string;             // 起涨 / 主升 / 顶部 / 下跌 / 筑底
  action: string;            // 持有 / 加仓 / 减仓 / 止损 / 观望
  action_rationale: string;
  trigger: string;
  technical: string;
  fundamental: string;
  risk: string;
}

export interface DailyParsed {
  positions: DailyPositionAdvice[];
  priorities: string[];
  portfolio_note: string;
}

export type DailySSEEvent =
  | { type: 'status'; data: { phase: string } }
  | { type: 'positions'; data: Position[] }
  | { type: 'market_env'; data: Record<string, string> }
  | { type: 'chunk'; data: { text: string } }
  | { type: 'parsed'; data: DailyParsed }
  | { type: 'done'; data: { review_id: number; latency_ms: number; engine: string; parse_error?: string | null } }
  | { type: 'error'; data: { message: string; type?: string } };

export async function* streamDailyReview(): AsyncGenerator<DailySSEEvent> {
  const resp = await authFetch('/api/daily/review/stream', {
    method: 'POST',
    headers: { 'Accept': 'text/event-stream' },
  });
  if (!resp.body) throw new Error('响应无 body');
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const part of parts) {
      const lines = part.split('\n');
      let ev = '';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data = line.slice(5).trim();
      }
      if (!ev || !data) continue;
      try {
        yield { type: ev as DailySSEEvent['type'], data: JSON.parse(data) } as DailySSEEvent;
      } catch {
        // skip
      }
    }
  }
}
