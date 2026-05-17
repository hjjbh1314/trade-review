import { useState } from 'react';
import type {
  TradeInput, Snapshot, RuleTag, Scores, Scenario, ParsedReview
} from '../api';
import { streamFlashReview } from '../api';

const MOODS = ['冷静', '兴奋', '犹豫', '恐惧', '贪婪', '报复'];

function severityBadge(s: string): string {
  return s === 'heavy' ? 'bg-down-100 text-down-500'
    : s === 'medium' ? 'bg-warn-100 text-warn-500'
      : 'bg-cream-200 text-ink-700';
}

function scoreColor(v: number): string {
  if (v >= 70) return 'text-up-500';
  if (v >= 50) return 'text-warn-500';
  return 'text-down-500';
}

function phaseText(phase: string): string {
  return {
    fetching_market: '拉取行情中...',
    tagging: '规则层打标签...',
    ai_generating: 'AI 分析中（冷启动约 30-50 秒）...',
  }[phase] ?? phase;
}

export function FlashPage() {
  const [form, setForm] = useState<TradeInput>({
    symbol: '', market: 'A', name: '', action: 'buy',
    price: 0, quantity: 0,
    trade_time: new Date().toISOString().slice(0, 16).replace('T', ' ') + ':00',
    reason: '', mood: '冷静',
  });
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [ruleTags, setRuleTags] = useState<RuleTag[]>([]);
  const [streamText, setStreamText] = useState('');
  const [parsed, setParsed] = useState<ParsedReview | null>(null);
  const [meta, setMeta] = useState<{ engine?: string; latency_ms?: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit() {
    if (!form.symbol || form.price <= 0 || form.quantity <= 0) {
      setErr('请填标的、价格、数量');
      return;
    }
    setLoading(true);
    setErr(null);
    setPhase(''); setSnapshot(null); setRuleTags([]);
    setStreamText(''); setParsed(null); setMeta(null);

    try {
      for await (const ev of streamFlashReview(form)) {
        switch (ev.type) {
          case 'status':   setPhase(ev.data.phase); break;
          case 'snapshot': setSnapshot(ev.data); break;
          case 'tags':     setRuleTags(ev.data); break;
          case 'chunk':    setStreamText(s => s + ev.data.text); break;
          case 'parsed':   setParsed(ev.data); break;
          case 'done':
            setMeta({ engine: ev.data.engine, latency_ms: ev.data.latency_ms });
            if (ev.data.parse_error) setErr(`JSON 解析警告: ${ev.data.parse_error}`);
            break;
          case 'error':    setErr(ev.data.message); break;
        }
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
      setPhase('');
    }
  }

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink-900">盘中闪评 · Flash Review</h1>
        <p className="text-sm text-ink-500">刚做完一笔交易？给你时机 + 心态 + 技术三维评分与证据。</p>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* 左：表单 */}
        <div className="col-span-5">
          <div className="bg-white border border-cream-300 rounded-xl p-5 space-y-4">
            <h2 className="font-semibold text-ink-900">本笔交易</h2>

            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-xs text-ink-500">标的代码</label>
                <input value={form.symbol}
                  onChange={e => setForm({ ...form, symbol: e.target.value.trim() })}
                  placeholder="600519 / 00700 / AAPL"
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
              </div>
              <div>
                <label className="text-xs text-ink-500">市场</label>
                <select value={form.market}
                  onChange={e => setForm({ ...form, market: e.target.value as TradeInput['market'] })}
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900">
                  <option value="A">A 股</option>
                  <option value="HK">港股</option>
                  <option value="US">美股</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-ink-500">名称（可选）</label>
                <input value={form.name ?? ''}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900" />
              </div>
              <div>
                <label className="text-xs text-ink-500">方向</label>
                <div className="flex gap-2 mt-1">
                  <button
                    onClick={() => setForm({ ...form, action: 'buy' })}
                    className={`flex-1 py-2 rounded text-sm font-semibold border ${
                      form.action === 'buy'
                        ? 'bg-up-100 text-up-500 border-up-500'
                        : 'border-cream-300 text-ink-500'}`}>
                    买入
                  </button>
                  <button
                    onClick={() => setForm({ ...form, action: 'sell' })}
                    className={`flex-1 py-2 rounded text-sm font-semibold border ${
                      form.action === 'sell'
                        ? 'bg-down-100 text-down-500 border-down-500'
                        : 'border-cream-300 text-ink-500'}`}>
                    卖出
                  </button>
                </div>
              </div>
              <div>
                <label className="text-xs text-ink-500">当前心态</label>
                <select value={form.mood}
                  onChange={e => setForm({ ...form, mood: e.target.value })}
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900">
                  {MOODS.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-ink-500">成交价</label>
                <input type="number" step="0.01" value={form.price || ''}
                  onChange={e => setForm({ ...form, price: parseFloat(e.target.value) || 0 })}
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
              </div>
              <div>
                <label className="text-xs text-ink-500">数量（股）</label>
                <input type="number" value={form.quantity || ''}
                  onChange={e => setForm({ ...form, quantity: parseInt(e.target.value) || 0 })}
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-ink-500">交易时间</label>
                <input value={form.trade_time}
                  onChange={e => setForm({ ...form, trade_time: e.target.value })}
                  placeholder="2026-04-24 14:20:00"
                  className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
              </div>
            </div>

            <div>
              <label className="text-xs text-ink-500">交易理由（一句话）</label>
              <textarea rows={2} value={form.reason ?? ''}
                onChange={e => setForm({ ...form, reason: e.target.value })}
                className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900" />
            </div>

            <button onClick={onSubmit} disabled={loading}
              className="w-full bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white font-semibold py-3 rounded-lg text-sm transition-colors">
              {loading ? '⚡ 分析中...' : '⚡ 生成闪评'}
            </button>

            {err && <div className="bg-down-100 text-down-500 text-xs px-3 py-2 rounded">{err}</div>}
          </div>
        </div>

        {/* 右：AI 输出 */}
        <div className="col-span-7 space-y-4">

          {/* 进度条 */}
          {loading && phase && (
            <div className="bg-white border border-cream-300 rounded-xl px-5 py-3 flex items-center gap-3">
              <div className="w-2 h-2 rounded-full bg-clay-500 animate-pulse"></div>
              <span className="text-sm text-ink-700">{phaseText(phase)}</span>
            </div>
          )}

          {/* 行情快照 */}
          {snapshot && !snapshot.error && (
            <div className="bg-white border border-cream-300 rounded-xl p-4">
              <h3 className="text-xs text-ink-400 mb-2">📊 行情快照</h3>
              <div className="grid grid-cols-4 gap-3 text-xs font-mono">
                <div><div className="text-ink-400">开盘</div><div className="text-ink-900">{snapshot.open ?? 'n/a'}</div></div>
                <div><div className="text-ink-400">当前</div><div className="text-ink-900">{snapshot.last ?? 'n/a'}</div></div>
                <div><div className="text-ink-400">日涨跌</div>
                  <div className={(snapshot.daily_change_pct ?? 0) >= 0 ? 'text-up-500' : 'text-down-500'}>
                    {snapshot.daily_change_pct ?? 'n/a'}%
                  </div>
                </div>
                <div><div className="text-ink-400">盘前30分</div>
                  <div className={(snapshot.pre30_change_pct ?? 0) >= 0 ? 'text-up-500' : 'text-down-500'}>
                    {snapshot.pre30_change_pct ?? 'n/a'}%
                  </div>
                </div>
                <div><div className="text-ink-400">MA5</div><div className="text-ink-900">{snapshot.ma5 ?? 'n/a'}</div></div>
                <div><div className="text-ink-400">MA20</div><div className="text-ink-900">{snapshot.ma20 ?? 'n/a'}</div></div>
                <div><div className="text-ink-400">MACD</div><div className="text-ink-900">{snapshot.macd_note ?? 'n/a'}</div></div>
                <div><div className="text-ink-400">RSI</div><div className="text-ink-900">{snapshot.rsi ?? 'n/a'}</div></div>
              </div>
              {snapshot.index_note && (
                <div className="text-xs text-ink-500 mt-2">大盘：{snapshot.index_note}</div>
              )}
            </div>
          )}

          {/* 规则标签 */}
          {ruleTags.length > 0 && (
            <div className="bg-white border border-cream-300 rounded-xl p-4">
              <h3 className="text-xs text-ink-400 mb-2">🏷️ 机器识别</h3>
              <div className="flex flex-wrap gap-2">
                {ruleTags.map((t, i) => (
                  <span key={i} className={`px-2 py-1 rounded text-xs font-medium ${severityBadge(t.severity)}`}>
                    {t.tag}（{t.severity}）
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 评分 */}
          {parsed?.scores && <ScoresCard scores={parsed.scores} meta={meta} />}

          {/* 心态诊断 */}
          {parsed?.mindset_reasoning && (
            <div className="bg-white border border-cream-300 rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-ink-900">心态诊断</h3>
                <div className="flex gap-1.5 flex-wrap">
                  {parsed.mindset_tags?.map((t, i) => (
                    <span key={i} className="bg-cream-200 text-ink-700 px-2 py-0.5 rounded text-xs">{t}</span>
                  ))}
                </div>
              </div>
              <p className="text-sm text-ink-700 leading-relaxed whitespace-pre-wrap">{parsed.mindset_reasoning}</p>
            </div>
          )}

          {/* 技术面 */}
          {parsed?.technical_reading && (
            <div className="bg-white border border-cream-300 rounded-xl p-5">
              <h3 className="font-semibold mb-2 text-ink-900">技术面解读</h3>
              <p className="text-sm text-ink-700 leading-relaxed whitespace-pre-wrap">{parsed.technical_reading}</p>
            </div>
          )}

          {/* 剧本 */}
          {parsed?.scenarios && parsed.scenarios.length > 0 && (
            <div className="bg-white border border-cream-300 rounded-xl p-5">
              <h3 className="font-semibold mb-3 text-ink-900">后续剧本</h3>
              <div className="space-y-3">
                {parsed.scenarios.map((s, i) => <ScenarioRow key={i} s={s} />)}
              </div>
            </div>
          )}

          {/* 一句话教训 */}
          {parsed?.one_line_lesson && (
            <div className="bg-white border border-cream-300 border-l-4 border-l-clay-500 rounded-xl p-5">
              <div className="text-xs text-ink-500 mb-1">💡 一句话教训</div>
              <div className="text-sm text-ink-900">{parsed.one_line_lesson}</div>
            </div>
          )}

          {/* 流式原文（fallback / 调试用） */}
          {streamText && !parsed && (
            <div className="bg-white border border-cream-300 rounded-xl p-5">
              <div className="text-xs text-ink-400 mb-2">AI 输出中...</div>
              <pre className="text-xs text-ink-700 whitespace-pre-wrap font-mono max-h-96 overflow-y-auto scrollbar-thin">{streamText}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ScoresCard({ scores, meta }: { scores: Scores; meta: { engine?: string; latency_ms?: number } | null }) {
  const items: Array<{ label: string; value: number }> = [
    { label: '时机', value: scores.timing },
    { label: '心态', value: scores.mindset },
    { label: '技术面', value: scores.technical },
  ];
  return (
    <div className="bg-white border border-cream-300 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-ink-900">综合评分</h3>
        {meta && (
          <span className="text-xs text-ink-400">
            {meta.engine} · {meta.latency_ms ? `${(meta.latency_ms / 1000).toFixed(1)}s` : ''}
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-4">
        {items.map(it => (
          <div key={it.label} className="text-center">
            <div className="text-xs text-ink-500 mb-1">{it.label}</div>
            <div className={`text-3xl font-mono font-semibold ${scoreColor(it.value)}`}>{it.value}</div>
            <div className="score-bar-bg mt-2">
              <div className="score-bar-fill"
                style={{
                  width: `${it.value}%`,
                  background: it.value >= 70 ? '#2D8659' : it.value >= 50 ? '#C48A1E' : '#C14D3F',
                }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScenarioRow({ s }: { s: Scenario }) {
  const tone =
    s.name.includes('乐观') ? 'bg-up-100 text-up-500' :
    s.name.includes('悲观') ? 'bg-down-100 text-down-500' :
    'bg-info-100 text-info-500';
  return (
    <div className="flex gap-3 items-start">
      <span className={`shrink-0 mt-0.5 px-2 py-0.5 rounded text-xs font-medium ${tone}`}>
        {s.name} {s.probability}%
      </span>
      <div className="text-xs text-ink-700 flex-1 leading-relaxed">
        <div><span className="text-ink-400">触发：</span>{s.trigger}</div>
        <div><span className="text-ink-400">操作：</span>{s.action}</div>
      </div>
    </div>
  );
}
