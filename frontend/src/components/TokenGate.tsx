import { useEffect, useState } from 'react';
import { getToken, setToken, checkAuthStatus, verifyToken } from '../api';

type Status = 'checking' | 'ok' | 'need-token';

/** 拦在全 App 最外层。若服务端要 token 且本地没有/错了，就显示输入界面。 */
export function TokenGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>('checking');
  const [input, setInput] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      // URL hash 注入（启动脚本打印的 URL 形如 .../#token=xxx）
      const hash = window.location.hash;
      const m = hash.match(/token=([A-Za-z0-9_-]+)/);
      if (m) {
        setToken(m[1]);
        // 清掉 URL 上的 token（留在 localStorage 即可）
        history.replaceState(null, '', window.location.pathname + window.location.search);
      }

      const s = await checkAuthStatus();
      if (!s.required) {
        setStatus('ok');
        return;
      }
      const token = getToken();
      if (!token) {
        setStatus('need-token');
        return;
      }
      const ok = await verifyToken(token);
      setStatus(ok ? 'ok' : 'need-token');
    })().catch(() => setStatus('need-token'));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const t = input.trim();
      if (!t) { setErr('请填 Token'); return; }
      const ok = await verifyToken(t);
      if (!ok) {
        setErr('Token 错误');
        return;
      }
      setToken(t);
      setStatus('ok');
    } finally {
      setBusy(false);
    }
  }

  if (status === 'checking') {
    return <div className="min-h-screen flex items-center justify-center text-ink-400">加载中...</div>;
  }
  if (status === 'ok') {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream-50 px-4">
      <div className="bg-white border border-cream-300 rounded-xl p-8 max-w-md w-full shadow">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-clay-500 flex items-center justify-center font-bold text-white text-lg">TR</div>
          <div>
            <div className="font-semibold text-ink-900">Trade Review</div>
            <div className="text-xs text-ink-500">本服务仅对持有 Token 的设备开放</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="text-xs text-ink-500">访问 Token</label>
            <input
              type="password"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="从终端启动日志 .tr_token 文件复制"
              className="w-full bg-white border border-cream-300 rounded px-3 py-2 text-sm mt-1 font-mono text-ink-900"
              autoFocus
            />
          </div>
          {err && <div className="bg-down-100 text-down-500 text-xs px-3 py-2 rounded">{err}</div>}
          <button type="submit" disabled={busy}
                  className="w-full bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white py-2.5 rounded text-sm font-semibold">
            {busy ? '验证中...' : '进入'}
          </button>
        </form>

        <div className="mt-5 text-xs text-ink-500 leading-relaxed">
          <p className="mb-1">💡 Token 在哪找：</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>项目根目录的 <code className="bg-cream-200 px-1 rounded">.tr_token</code> 文件</li>
            <li>启动脚本打印的 URL 末尾 <code className="bg-cream-200 px-1 rounded">#token=XXX</code></li>
            <li>验证成功后会记住 7 天，下次免输入</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
