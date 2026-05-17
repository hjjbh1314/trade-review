import { useState } from 'react';
import type { Position, Market } from '../api';

export function AddPositionModal({ onClose, onSubmit }: {
  onClose: () => void;
  onSubmit: (p: Omit<Position, 'id' | 'updated_at'>) => void | Promise<void>;
}) {
  const [form, setForm] = useState({
    symbol: '', market: 'A' as Market, name: '',
    quantity: 0, cost_price: 0,
  });
  const [err, setErr] = useState<string | null>(null);

  function submit() {
    if (!form.symbol) return setErr('填标的代码');
    if (form.quantity <= 0) return setErr('数量需 > 0');
    if (form.cost_price <= 0) return setErr('成本价需 > 0');
    setErr(null);
    onSubmit(form);
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl border border-cream-300 p-6 w-[420px]"
           onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-ink-900 mb-4">添加持仓</h2>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-ink-500">标的代码</label>
            <input value={form.symbol}
              onChange={e => setForm({ ...form, symbol: e.target.value.trim() })}
              placeholder="600519 / 00700 / AAPL"
              className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-ink-500">市场</label>
              <select value={form.market}
                onChange={e => setForm({ ...form, market: e.target.value as Market })}
                className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900">
                <option value="A">A 股</option>
                <option value="HK">港股</option>
                <option value="US">美股</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-ink-500">名称（可选）</label>
              <input value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 text-ink-900" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-ink-500">数量（股）</label>
              <input type="number" value={form.quantity || ''}
                onChange={e => setForm({ ...form, quantity: parseInt(e.target.value) || 0 })}
                className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
            </div>
            <div>
              <label className="text-xs text-ink-500">成本价</label>
              <input type="number" step="0.01" value={form.cost_price || ''}
                onChange={e => setForm({ ...form, cost_price: parseFloat(e.target.value) || 0 })}
                className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900" />
            </div>
          </div>

          {err && <div className="bg-down-100 text-down-500 text-xs px-3 py-2 rounded">{err}</div>}

          <div className="flex gap-2 pt-2">
            <button onClick={onClose}
                    className="flex-1 border border-cream-300 text-ink-700 py-2 rounded text-sm hover:bg-cream-100">
              取消
            </button>
            <button onClick={submit}
                    className="flex-1 bg-clay-500 hover:bg-clay-600 text-white py-2 rounded text-sm font-semibold">
              添加
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
