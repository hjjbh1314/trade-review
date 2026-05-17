import { useCallback, useEffect, useState } from 'react';
import type { WeeklyMindset, MindsetRadar, MindsetError } from '../api';
import { fetchWeeklyMindset, fetchAvailableWeeks } from '../api';

const AXIS_LABELS: Array<{ key: keyof MindsetRadar; label: string }> = [
  { key: 'discipline', label: '纪律性' },
  { key: 'emotion',    label: '情绪稳定' },
  { key: 'risk_ctrl',  label: '风控执行' },
  { key: 'autonomy',   label: '独立判断' },
  { key: 'patience',   label: '耐心' },
  { key: 'learning',   label: '学习力' },
];

function scoreColor(v: number): string {
  if (v >= 75) return 'text-up-500';
  if (v >= 55) return 'text-warn-500';
  return 'text-down-500';
}

function severityBadge(s: string): string {
  return s === 'heavy' ? 'bg-down-100 text-down-500'
    : s === 'medium' ? 'bg-warn-100 text-warn-500'
      : 'bg-cream-200 text-ink-700';
}

export function MindsetPage() {
  const [data, setData] = useState<WeeklyMindset | null>(null);
  const [weeks, setWeeks] = useState<Array<{ year_week: string; start: string; end: string }>>([]);
  const [currentWeek, setCurrentWeek] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchAvailableWeeks(12).then(setWeeks).catch(() => {});
  }, []);

  const load = useCallback(async (week?: string) => {
    setLoading(true);
    setErr(null);
    try {
      const d = await fetchWeeklyMindset(week);
      setData(d);
      setCurrentWeek(d.year_week);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-ink-900 mb-1">
            周度心态画像{data ? ` · ${data.year_week}` : ''}
          </h1>
          <p className="text-sm text-ink-500">
            {data ? `${data.week_start} ~ ${data.week_end} · 本周 ${data.trade_count} 笔交易` : '基于本周交易结构化诊断'}
          </p>
        </div>
        <div className="flex gap-2">
          <select value={currentWeek}
                  onChange={e => load(e.target.value)}
                  className="bg-white border border-cream-300 rounded px-3 py-1.5 text-sm">
            {weeks.map(w => (
              <option key={w.year_week} value={w.year_week}>
                {w.year_week}  ·  {w.start.slice(5)} ~ {w.end.slice(5)}
              </option>
            ))}
          </select>
          <button onClick={() => load(currentWeek)} disabled={loading}
                  className="bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm">
            {loading ? '生成中...' : '重新生成'}
          </button>
        </div>
      </div>

      {err && <div className="bg-down-100 text-down-500 text-sm px-4 py-2 rounded mb-4">{err}</div>}

      {!data && loading && (
        <div className="text-center py-12 text-ink-400">生成中...</div>
      )}

      {data && data.trade_count === 0 && (
        <div className="bg-white border border-cream-300 rounded-xl p-12 text-center text-ink-400">
          本周无交易记录，没有可分析数据。<br />
          去"盘中闪评"或"每日复盘"产生一些交易后再来看。
        </div>
      )}

      {data && data.trade_count > 0 && (
        <div className="grid grid-cols-12 gap-6">
          {/* 左：雷达 */}
          <div className="col-span-5">
            <div className="bg-white border border-cream-300 rounded-xl p-5">
              <h2 className="font-semibold text-ink-900 mb-4">心态雷达</h2>
              <RadarChart radar={data.radar} />
              <div className="grid grid-cols-2 gap-2 mt-4 text-xs">
                {AXIS_LABELS.map(a => (
                  <div key={a.key} className="flex justify-between">
                    <span className="text-ink-500">{a.label}</span>
                    <span className={`font-mono ${scoreColor(data.radar[a.key])}`}>{data.radar[a.key]}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右：标签云 + 典型错误 + AI 寄语 */}
          <div className="col-span-7 space-y-4">
            <TagCloud tagCounts={data.tag_counts} />
            <TopErrors errors={data.top_errors} />
            {data.ai_message && (
              <div className="bg-white border border-cream-300 border-l-4 border-l-clay-500 rounded-xl p-5">
                <div className="text-xs text-ink-500 mb-2">🎓 AI 本周寄语</div>
                <p className="text-sm text-ink-700 leading-relaxed whitespace-pre-wrap">{data.ai_message}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RadarChart({ radar }: { radar: MindsetRadar }) {
  const size = 300;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size * 0.38;

  // 6 个轴，从 12 点钟开始顺时针
  const points = AXIS_LABELS.map((a, i) => {
    const angle = (Math.PI * 2 * i) / AXIS_LABELS.length - Math.PI / 2;
    const value = radar[a.key] / 100;
    const x = cx + Math.cos(angle) * maxR * value;
    const y = cy + Math.sin(angle) * maxR * value;
    const axisX = cx + Math.cos(angle) * maxR;
    const axisY = cy + Math.sin(angle) * maxR;
    const labelX = cx + Math.cos(angle) * (maxR + 22);
    const labelY = cy + Math.sin(angle) * (maxR + 22);
    return { x, y, axisX, axisY, labelX, labelY, label: a.label, angle };
  });

  const polygon = points.map(p => `${p.x},${p.y}`).join(' ');

  // 背景六边形刻度线（40 / 70 / 100）
  const gridLevels = [0.4, 0.7, 1.0];

  return (
    <div className="relative aspect-square bg-cream-100 rounded-lg flex items-center justify-center border border-cream-300">
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full">
        {/* 刻度线 */}
        {gridLevels.map(level => {
          const pts = AXIS_LABELS.map((_, i) => {
            const angle = (Math.PI * 2 * i) / AXIS_LABELS.length - Math.PI / 2;
            return `${cx + Math.cos(angle) * maxR * level},${cy + Math.sin(angle) * maxR * level}`;
          }).join(' ');
          return <polygon key={level} points={pts} fill="none" stroke="#C9C4B2" strokeWidth="1" />;
        })}

        {/* 轴线 */}
        {points.map((p, i) => (
          <line key={i} x1={cx} y1={cy} x2={p.axisX} y2={p.axisY} stroke="#C9C4B2" strokeWidth="1" />
        ))}

        {/* 数据多边形 */}
        <polygon points={polygon} fill="#D97757" fillOpacity="0.22" stroke="#D97757" strokeWidth="2" />

        {/* 节点 */}
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#D97757" />
        ))}

        {/* 标签 */}
        {points.map((p, i) => (
          <text key={i} x={p.labelX} y={p.labelY}
                fontSize="11" fill="#6B6855" fontFamily="sans-serif"
                textAnchor="middle" dominantBaseline="middle">
            {p.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

function TagCloud({ tagCounts }: { tagCounts: Record<string, number> }) {
  const entries = Object.entries(tagCounts);
  return (
    <div className="bg-white border border-cream-300 rounded-xl p-5">
      <h2 className="font-semibold text-ink-900 mb-3">本周行为标签</h2>
      {entries.length === 0 ? (
        <div className="text-xs text-ink-400">本周零负面标签，情绪表现完美。</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {entries
            .sort((a, b) => b[1] - a[1])
            .map(([tag, n]) => {
              const bad = ['追涨', '杀跌', '拖单', '报复性交易', '逆势', '频繁交易', '过早止盈'].includes(tag);
              const cls = bad ? 'bg-down-100 text-down-500' : 'bg-up-100 text-up-500';
              return (
                <span key={tag} className={`${cls} px-2 py-1 rounded text-xs font-medium`}>
                  {tag} × {n}
                </span>
              );
            })}
        </div>
      )}
    </div>
  );
}

function TopErrors({ errors }: { errors: MindsetError[] }) {
  return (
    <div className="bg-white border border-cream-300 rounded-xl">
      <div className="px-5 py-3 border-b border-cream-300">
        <h2 className="font-semibold text-ink-900">本周 {errors.length} 个典型错误</h2>
      </div>
      {errors.length === 0 ? (
        <div className="p-5 text-sm text-ink-400">本周没有触发典型错误 ✓</div>
      ) : (
        <div className="divide-y divide-cream-300">
          {errors.map((e, i) => (
            <div key={i} className="p-4 flex gap-3">
              <div className={`w-8 h-8 rounded-full ${
                e.severity === 'heavy' ? 'bg-down-100 text-down-500'
                : e.severity === 'medium' ? 'bg-warn-100 text-warn-500'
                : 'bg-cream-200 text-ink-700'
              } flex items-center justify-center text-sm font-bold shrink-0`}>
                {i + 1}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-ink-900 mb-1">
                  {e.trade_time?.slice(5, 16)}  {e.symbol}
                  <span className={`text-xs ml-2 px-2 py-0.5 rounded ${severityBadge(e.severity)}`}>
                    {e.tag}（{e.severity}）
                  </span>
                </div>
                {Object.keys(e.evidence).length > 0 && (
                  <div className="text-xs text-ink-500 font-mono">
                    证据：{Object.entries(e.evidence).map(([k, v]) => `${k}=${v}`).join(' · ')}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
