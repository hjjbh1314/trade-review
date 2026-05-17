import { useState } from 'react';
import type { Position, DailyParsed, DailyPositionAdvice, Market } from '../api';
import { streamDailyReview } from '../api';

function phaseText(phase: string): string {
  return {
    fetching_positions: '拉取持仓和行情中...',
    ai_generating: 'AI 综合分析中（约 20-40 秒）...',
  }[phase] ?? phase;
}

function marketLabel(m: Market): string {
  return { A: 'A股', HK: '港股', US: '美股' }[m] ?? m;
}

function actionTone(action: string): string {
  if (action.includes('加仓')) return 'bg-up-100 text-up-500';
  if (action.includes('止损') || action.includes('减仓')) return 'bg-down-100 text-down-500';
  if (action.includes('观望') || action.includes('持有')) return 'bg-info-100 text-info-500';
  return 'bg-cream-200 text-ink-700';
}

function stageTone(stage: string): string {
  if (stage.includes('起涨') || stage.includes('主升')) return 'bg-up-100 text-up-500';
  if (stage.includes('下跌') || stage.includes('顶部')) return 'bg-down-100 text-down-500';
  return 'bg-warn-100 text-warn-500';
}

export function DailyPage() {
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('');
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [env, setEnv] = useState<Record<string, string>>({});
  const [streamText, setStreamText] = useState('');
  const [parsed, setParsed] = useState<DailyParsed | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ engine?: string; latency_ms?: number } | null>(null);

  async function onStart() {
    setLoading(true);
    setErr(null);
    setPhase(''); setPositions(null); setEnv({});
    setStreamText(''); setParsed(null); setMeta(null);
    try {
      for await (const ev of streamDailyReview()) {
        switch (ev.type) {
          case 'status':     setPhase(ev.data.phase); break;
          case 'positions':  setPositions(ev.data); break;
          case 'market_env': setEnv(ev.data); break;
          case 'chunk':      setStreamText(s => s + ev.data.text); break;
          case 'parsed':     setParsed(ev.data); break;
          case 'done':       setMeta({ engine: ev.data.engine, latency_ms: ev.data.latency_ms });
                             if (ev.data.parse_error) setErr(`解析警告: ${ev.data.parse_error}`);
                             break;
          case 'error':      setErr(ev.data.message); break;
        }
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
      setPhase('');
    }
  }

  // 把 positions 和 parsed.positions 通过 symbol+market 合并渲染
  const merged = (() => {
    if (!positions) return null;
    return positions.map(p => {
      const advice = parsed?.positions?.find(
        a => a.symbol === p.symbol && a.market === p.market
      );
      return { pos: p, advice };
    });
  })();

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-ink-900 mb-1">每日复盘 · {today}</h1>
          <p className="text-sm text-ink-500">基于当前持仓生成明日操作建议，覆盖 A 股 / 港股 / 美股。</p>
        </div>
        <button onClick={onStart} disabled={loading}
                className="bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white font-semibold px-5 py-2 rounded-lg text-sm">
          {loading ? '分析中...' : '🔍 开始复盘'}
        </button>
      </div>

      {loading && phase && (
        <div className="bg-white border border-cream-300 rounded-xl px-5 py-3 mb-4 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-clay-500 animate-pulse"></div>
          <span className="text-sm text-ink-700">{phaseText(phase)}</span>
        </div>
      )}

      {err && (
        <div className="bg-down-100 text-down-500 text-sm px-4 py-2 rounded mb-4">{err}</div>
      )}

      {/* 市场环境 */}
      {Object.keys(env).length > 0 && (
        <div className="bg-white border border-cream-300 rounded-xl p-4 mb-6">
          <h2 className="text-sm font-semibold text-ink-900 mb-2">市场环境</h2>
          <div className="grid grid-cols-3 gap-4 text-sm">
            {env.a_index && <div><div className="text-xs text-ink-400">A 股</div><div className="font-mono text-ink-900">{env.a_index}</div></div>}
            {env.hk_index && <div><div className="text-xs text-ink-400">港股</div><div className="font-mono text-ink-900">{env.hk_index}</div></div>}
            {env.us_index && <div><div className="text-xs text-ink-400">美股</div><div className="font-mono text-ink-900">{env.us_index}</div></div>}
          </div>
        </div>
      )}

      {/* 持仓分块 */}
      {merged && (
        <div className="space-y-4">
          {merged.map(({ pos, advice }) => (
            <PositionCard key={`${pos.market}-${pos.symbol}`} pos={pos} advice={advice} />
          ))}
        </div>
      )}

      {/* 优先级 */}
      {parsed?.priorities && parsed.priorities.length > 0 && (
        <div className="bg-white border border-cream-300 border-l-4 border-l-clay-500 rounded-xl p-5 mt-6">
          <h2 className="font-semibold text-ink-900 mb-3">🎯 明日要点（按优先级）</h2>
          <ol className="text-sm text-ink-700 space-y-1.5 list-decimal list-inside">
            {parsed.priorities.map((p, i) => <li key={i}>{p}</li>)}
          </ol>
        </div>
      )}

      {/* 组合评价 */}
      {parsed?.portfolio_note && (
        <div className="bg-white border border-cream-300 rounded-xl p-5 mt-4">
          <div className="text-xs text-ink-400 mb-1">💼 组合评价</div>
          <p className="text-sm text-ink-700 leading-relaxed">{parsed.portfolio_note}</p>
        </div>
      )}

      {/* 未解析的流式原文 */}
      {streamText && !parsed && (
        <div className="bg-white border border-cream-300 rounded-xl p-5 mt-4">
          <div className="text-xs text-ink-400 mb-2">AI 正在输出...</div>
          <pre className="text-xs text-ink-700 whitespace-pre-wrap font-mono max-h-96 overflow-y-auto scrollbar-thin">{streamText}</pre>
        </div>
      )}

      {meta && (
        <div className="text-xs text-ink-400 mt-4 text-right">
          {meta.engine} · {meta.latency_ms ? `${(meta.latency_ms / 1000).toFixed(1)}s` : ''}
        </div>
      )}

      {!loading && !positions && (
        <div className="bg-white border border-cream-300 rounded-xl p-12 text-center text-ink-400">
          <div className="mb-3">还没生成复盘。</div>
          <div className="text-sm">请确保已在仪表盘添加持仓，然后点"开始复盘"。</div>
        </div>
      )}
    </div>
  );
}

function PositionCard({ pos, advice }: {
  pos: Position;
  advice?: DailyPositionAdvice;
}) {
  const pnlColor = (pos.pnl_pct ?? 0) >= 0 ? 'text-up-500' : 'text-down-500';
  return (
    <div className="bg-white border border-cream-300 rounded-xl">
      <div className="flex items-center justify-between px-5 py-3 border-b border-cream-300">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-base text-ink-900">{pos.name ?? pos.symbol}</span>
          <span className="text-xs text-ink-400 font-mono">{pos.symbol} · {marketLabel(pos.market)}</span>
          {advice && (
            <>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${stageTone(advice.stage)}`}>{advice.stage}</span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${actionTone(advice.action)}`}>{advice.action}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm font-mono">
          <span className="text-ink-500">成本 {pos.cost_price} × {pos.quantity}</span>
          <span className={pnlColor}>
            {pos.pnl_pct != null ? `${pos.pnl_pct >= 0 ? '+' : ''}${pos.pnl_pct.toFixed(2)}%` : '—'}
          </span>
        </div>
      </div>
      {!advice ? (
        <div className="p-5 text-sm text-ink-400">AI 输出中，当前尚未解析出本持仓的具体建议...</div>
      ) : (
        <div className="grid grid-cols-12 gap-4 p-5">
          <div className="col-span-4">
            <div className="text-xs text-ink-400 mb-2">📌 明日操作</div>
            <div className="text-sm font-semibold text-clay-500 mb-1">{advice.action}</div>
            <div className="text-xs text-ink-700 leading-relaxed">{advice.action_rationale}</div>
            {advice.trigger && (
              <div className="text-xs text-ink-500 mt-2">
                <span className="text-ink-400">触发：</span>{advice.trigger}
              </div>
            )}
          </div>
          <div className="col-span-4 border-l border-r border-cream-300 px-4">
            <div className="text-xs text-ink-400 mb-2">📊 技术</div>
            <p className="text-xs text-ink-700 leading-relaxed whitespace-pre-wrap">{advice.technical}</p>
          </div>
          <div className="col-span-4">
            <div className="text-xs text-ink-400 mb-2">📰 基本面 / 风险</div>
            <p className="text-xs text-ink-700 leading-relaxed">{advice.fundamental}</p>
            {advice.risk && (
              <p className="text-xs text-down-500 mt-2">⚠ {advice.risk}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
