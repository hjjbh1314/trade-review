import { useCallback, useEffect, useMemo, useState } from 'react';
import type { JournalItem, JournalTag } from '../api';
import { fetchJournal } from '../api';

const KNOWN_TAGS = [
  '追涨', '杀跌', '过早止盈', '拖单', '报复性交易', '逆势', '频繁交易',
];

function severityBadge(s: string): string {
  return s === 'heavy' ? 'bg-down-100 text-down-500'
    : s === 'medium' ? 'bg-warn-100 text-warn-500'
      : 'bg-cream-200 text-ink-700';
}

function actionTone(action: string): string {
  return action === 'buy' ? 'text-up-500' : 'text-down-500';
}

function actionLabel(action: string): string {
  return action === 'buy' ? '买入' : '卖出';
}

function marketLabel(m: string): string {
  return { A: 'A股', HK: '港股', US: '美股' }[m] ?? m;
}

export function JournalPage() {
  const [items, setItems] = useState<JournalItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [symbolFilter, setSymbolFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await fetchJournal(
        symbolFilter.trim() || undefined,
        tagFilter || undefined,
      );
      setItems(data);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, [symbolFilter, tagFilter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  // 所有可见的唯一标的（供筛选下拉）
  const uniqueSymbols = useMemo(() => {
    if (!items) return [];
    const s = new Set(items.map(i => `${i.market}/${i.symbol}`));
    return Array.from(s).sort();
  }, [items]);

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-ink-900 mb-1">交易日志</h1>
          <p className="text-sm text-ink-500">按时间倒序浏览所有交易 + 心态标签 + 闪评链接。</p>
        </div>
        <button onClick={load} disabled={loading}
                className="bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm">
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {/* 筛选栏 */}
      <div className="flex items-center gap-3 mb-4 text-sm">
        <input
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value.trim())}
          onKeyDown={e => e.key === 'Enter' && load()}
          placeholder="按标的筛选（600519 / 00700 / AAPL）"
          className="bg-white border border-cream-300 rounded px-3 py-1.5 font-mono text-ink-900 w-64"
        />
        <select value={tagFilter} onChange={e => setTagFilter(e.target.value)}
                className="bg-white border border-cream-300 rounded px-3 py-1.5 text-ink-900">
          <option value="">全部标签</option>
          {KNOWN_TAGS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        {uniqueSymbols.length > 0 && (
          <span className="text-xs text-ink-400">
            当前共 {items?.length ?? 0} 笔 · 涉及 {uniqueSymbols.length} 只标的
          </span>
        )}
      </div>

      {err && (
        <div className="bg-down-100 text-down-500 text-sm px-4 py-2 rounded mb-4">{err}</div>
      )}

      {items && items.length === 0 && (
        <div className="bg-white border border-cream-300 rounded-xl p-12 text-center text-ink-400">
          没有符合条件的交易。
        </div>
      )}

      {items && items.length > 0 && (
        <div className="bg-white border border-cream-300 rounded-xl">
          {items.map((it, i) => (
            <TimelineRow key={it.id}
                         item={it}
                         showTopLine={i > 0}
                         showBottomLine={i < items.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, showTopLine, showBottomLine }: {
  item: JournalItem;
  showTopLine: boolean;
  showBottomLine: boolean;
}) {
  const scores = item.review?.scores_json ? safeParse<{timing: number; mindset: number; technical: number}>(item.review.scores_json) : null;

  return (
    <div className="p-4 flex gap-4 hover:bg-cream-100 border-b border-cream-200 last:border-b-0">
      <div className="w-20 shrink-0 text-right">
        <div className="text-xs text-ink-400">{item.trade_time.slice(5, 10)}</div>
        <div className="text-xs font-mono text-ink-900">{item.trade_time.slice(11, 16)}</div>
      </div>
      <div className="w-2 shrink-0 flex flex-col items-center">
        <div className={`w-px ${showTopLine ? 'bg-cream-300' : 'bg-transparent'} flex-1 mb-1`} />
        <div className={`w-2 h-2 rounded-full ${item.action === 'buy' ? 'bg-up-500' : 'bg-down-500'}`} />
        <div className={`w-px ${showBottomLine ? 'bg-cream-300' : 'bg-transparent'} flex-1 mt-1`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className={`text-sm font-semibold ${actionTone(item.action)}`}>{actionLabel(item.action)}</span>
          <span className="text-sm font-semibold text-ink-900">{item.name ?? item.symbol}</span>
          <span className="text-xs text-ink-400 font-mono">{item.symbol} · {marketLabel(item.market)}</span>
          {item.mood && <span className="text-xs text-ink-500 border border-cream-300 px-1.5 py-0.5 rounded">心态：{item.mood}</span>}
          {item.tags.map((t: JournalTag, i: number) => (
            <span key={i} className={`text-xs px-2 py-0.5 rounded font-medium ${severityBadge(t.severity)}`}>
              {t.tag}（{t.severity}）
            </span>
          ))}
        </div>
        <div className="text-xs text-ink-700 font-mono">
          {item.quantity} 股 @ {item.price} · 共 {(item.quantity * item.price).toFixed(2)}
        </div>
        {item.reason && (
          <div className="text-xs text-ink-700 mt-1">理由：{item.reason}</div>
        )}
        {scores && (
          <div className="text-xs text-ink-500 mt-2">
            <span className="text-clay-500 font-medium">闪评</span>
            <span> 时机 {scores.timing} / 心态 {scores.mindset} / 技术 {scores.technical}</span>
          </div>
        )}
        {item.review?.lesson && (
          <div className="text-xs text-ink-700 mt-1 bg-cream-100 px-2 py-1 rounded border-l-2 border-clay-500">
            💡 {item.review.lesson}
          </div>
        )}
      </div>
    </div>
  );
}

function safeParse<T>(s: string): T | null {
  try { return JSON.parse(s) as T; } catch { return null; }
}
