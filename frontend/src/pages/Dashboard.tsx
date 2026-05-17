import { useEffect, useRef, useState, useCallback } from 'react';
import type { Position, MarketSummary, Market } from '../api';
import { fetchPositionsWithQuotes, createPosition, deletePosition } from '../api';
import { AddPositionModal } from '../components/AddPositionModal';
import { KLineChart } from '../components/KLineChart';
import { ChatPanel } from '../components/ChatPanel';

export function DashboardPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftPct, setLeftPct] = useState<number>(() => {
    const saved = parseFloat(localStorage.getItem('tr-split-left') ?? '');
    return !isNaN(saved) && saved >= 35 && saved <= 80 ? saved : 66.6;
  });
  const [dragging, setDragging] = useState(false);

  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<Record<string, MarketSummary>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState<Position | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const d = await fetchPositionsWithQuotes();
      setPositions(d.items);
      setSummary(d.summary);
      setSelected(current => current ?? d.items[0] ?? null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial data sync on mount; follow-up refreshes are user-triggered.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      let pct = ((e.clientX - rect.left) / rect.width) * 100;
      pct = Math.max(35, Math.min(80, pct));
      setLeftPct(pct);
    };
    const onUp = () => {
      setDragging(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      localStorage.setItem('tr-split-left', leftPct.toFixed(2));
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [dragging, leftPct]);

  async function onDelete(p: Position) {
    if (!confirm(`确认删除持仓 ${p.name ?? p.symbol}？`)) return;
    try {
      await deletePosition(p.market, p.symbol);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  }

  async function onAdd(data: Omit<Position, 'id' | 'updated_at'>) {
    try {
      await createPosition(data);
      setShowAdd(false);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  }

  // 汇总 KPI
  const totalPnl = Object.values(summary).reduce((s, m) => s + m.pnl, 0);
  const totalValue = Object.values(summary).reduce((s, m) => s + m.market_value, 0);
  const totalCount = Object.values(summary).reduce((s, m) => s + m.count, 0);
  const pnlPct = totalValue > 0 ? (totalPnl / (totalValue - totalPnl)) * 100 : 0;
  const marketCounts = Object.entries(summary)
    .map(([m, s]) => `${marketLabel(m as Market)} ${s.count}`)
    .join(' · ') || '无持仓';

  return (
    <div className="p-6 max-w-[1600px] mx-auto">

      {/* KPI */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KPI label="持仓市值（不跨币种换算）" value={fmt(totalValue)} hint={marketCounts} />
        <KPI label="累计盈亏" value={(totalPnl >= 0 ? '+' : '') + fmt(totalPnl)}
             tone={totalPnl >= 0 ? 'up' : 'down'}
             hint={`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`} />
        <KPI label="持仓数" value={String(totalCount)} hint="—" />
        <KPI label="本周交易笔数" value="—" hint="P4 对接" />
        <KPI label="心态分（本周）" value="—" hint="P4 生成" />
      </div>

      {err && (
        <div className="mb-4 bg-down-100 text-down-500 text-sm px-4 py-2 rounded">
          {err}
        </div>
      )}

      {/* 左右布局 */}
      <div ref={containerRef} className="flex gap-0" style={{ minHeight: 'calc(100vh - 280px)' }}>
        <div className="space-y-6 min-w-0 pr-3" style={{ flex: `0 0 ${leftPct}%` }}>
          <PositionsTable positions={positions} loading={loading} selected={selected}
                          onAdd={() => setShowAdd(true)} onDelete={onDelete} onRefresh={load}
                          onSelect={setSelected} />
          {selected ? (
            <KLineChart symbol={selected.symbol} market={selected.market} name={selected.name} />
          ) : (
            <KLinePlaceholder />
          )}
        </div>

        <div
          className={`resizer ${dragging ? 'dragging' : ''}`}
          onMouseDown={() => {
            setDragging(true);
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
          }}
          onDoubleClick={() => {
            setLeftPct(66.6);
            localStorage.removeItem('tr-split-left');
          }}
          title="拖拽调整宽度，双击重置"
        />

        <div className="min-w-0 pl-3" style={{ flex: '1 1 auto' }}>
          <ChatPanel focus={selected ? {
            symbol: selected.symbol,
            market: selected.market,
            name: selected.name,
            cost_price: selected.cost_price,
            quantity: selected.quantity,
          } : null} />
        </div>
      </div>

      {showAdd && <AddPositionModal onClose={() => setShowAdd(false)} onSubmit={onAdd} />}
    </div>
  );
}

function KPI({ label, value, hint, tone }: {
  label: string; value: string; hint: string;
  tone?: 'up' | 'down' | 'warn';
}) {
  const color = tone === 'up' ? 'text-up-500'
              : tone === 'down' ? 'text-down-500'
              : tone === 'warn' ? 'text-warn-500'
              : 'text-ink-900';
  return (
    <div className="bg-white border border-cream-300 rounded-xl p-4">
      <div className="text-xs text-ink-400 mb-1">{label}</div>
      <div className={`text-2xl font-mono font-semibold ${color}`}>{value}</div>
      <div className="text-xs text-ink-400 mt-1">{hint}</div>
    </div>
  );
}

function PositionsTable({ positions, loading, selected, onAdd, onDelete, onRefresh, onSelect }: {
  positions: Position[]; loading: boolean; selected: Position | null;
  onAdd: () => void; onDelete: (p: Position) => void; onRefresh: () => void;
  onSelect: (p: Position) => void;
}) {
  return (
    <div className="bg-white border border-cream-300 rounded-xl">
      <div className="flex items-center justify-between px-5 py-3 border-b border-cream-300">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-ink-900">当前持仓</h2>
          <span className="text-xs text-ink-400">
            {loading ? '加载中...' : `共 ${positions.length} 只`}
          </span>
        </div>
        <div className="flex gap-2 text-xs">
          <button onClick={onRefresh}
                  className="px-2.5 py-1 border border-cream-300 rounded hover:bg-cream-100 text-ink-700">
            刷新
          </button>
          <button onClick={onAdd}
                  className="px-3 py-1 bg-clay-500 hover:bg-clay-600 text-white rounded font-medium">
            + 添加持仓
          </button>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="p-12 text-center text-ink-400 text-sm">
          还没有持仓，点"+ 添加持仓"开始。
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-xs text-ink-400">
            <tr className="border-b border-cream-300">
              <th className="text-left px-5 py-2 font-normal">标的</th>
              <th className="text-right px-2 py-2 font-normal">持仓</th>
              <th className="text-right px-2 py-2 font-normal">成本</th>
              <th className="text-right px-2 py-2 font-normal">现价</th>
              <th className="text-right px-2 py-2 font-normal">日涨跌</th>
              <th className="text-right px-2 py-2 font-normal">盈亏%</th>
              <th className="text-right px-2 py-2 font-normal">市值</th>
              <th className="text-right px-5 py-2 font-normal"></th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {positions.map(p => (
              <tr key={p.id}
                  onClick={() => onSelect(p)}
                  className={`border-b border-cream-200 cursor-pointer ${
                    selected?.id === p.id ? 'bg-clay-100' : 'hover:bg-cream-100'}`}>
                <td className="px-5 py-3">
                  <div className="font-semibold text-ink-900 font-sans">{p.name ?? p.symbol}</div>
                  <div className="text-xs text-ink-400">{p.symbol} · {marketLabel(p.market)}</div>
                </td>
                <td className="text-right px-2">{p.quantity}</td>
                <td className="text-right px-2">{fmt(p.cost_price)}</td>
                <td className="text-right px-2">{p.last_price ? fmt(p.last_price) : '—'}</td>
                <td className={`text-right px-2 ${(p.daily_change_pct ?? 0) >= 0 ? 'text-up-500' : 'text-down-500'}`}>
                  {p.daily_change_pct != null ? `${p.daily_change_pct >= 0 ? '+' : ''}${p.daily_change_pct.toFixed(2)}%` : '—'}
                </td>
                <td className={`text-right px-2 ${(p.pnl_pct ?? 0) >= 0 ? 'text-up-500' : 'text-down-500'}`}>
                  {p.pnl_pct != null ? `${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct.toFixed(2)}%` : '—'}
                </td>
                <td className="text-right px-2">{p.market_value ? fmt(p.market_value) : '—'}</td>
                <td className="text-right px-5">
                  <button onClick={e => { e.stopPropagation(); onDelete(p); }}
                          className="text-xs text-ink-400 hover:text-down-500">×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function KLinePlaceholder() {
  return (
    <div className="bg-white border border-cream-300 rounded-xl">
      <div className="flex items-center justify-between px-5 py-3 border-b border-cream-300">
        <h2 className="font-semibold text-ink-900">K 线图</h2>
        <span className="text-xs text-ink-400">选中持仓查看 · 下一阶段接 lightweight-charts</span>
      </div>
      <div className="h-64 flex items-center justify-center text-ink-400 text-sm">
        📈 K 线图占位
      </div>
    </div>
  );
}

// ─── Utils ─────────────────────────────────────────────────────
function fmt(n: number): string {
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function marketLabel(m: Market | string): string {
  return { A: 'A股', HK: '港股', US: '美股' }[m as Market] ?? m;
}
