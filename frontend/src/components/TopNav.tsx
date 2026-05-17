import { NavLink } from 'react-router-dom';

const tabs = [
  { path: '/', label: '仪表盘' },
  { path: '/flash', label: '盘中闪评' },
  { path: '/daily', label: '每日复盘' },
  { path: '/mindset', label: '周度心态' },
  { path: '/journal', label: '交易日志' },
];

// Vite-injected build-time constant; falls back to empty so the badge hides.
const userName = (import.meta.env.VITE_USER_NAME ?? '').trim();

export function TopNav() {
  const now = new Date().toISOString().replace('T', ' ').slice(0, 16);
  return (
    <header className="sticky top-0 z-40 bg-cream-50/90 backdrop-blur border-b border-cream-300">
      <div className="flex items-center justify-between px-6">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 py-2">
            <div className="w-8 h-8 rounded-lg bg-clay-500 flex items-center justify-center font-bold text-white">
              TR
            </div>
            <span className="font-semibold tracking-wide text-ink-900">Trade Review</span>
            {userName && (
              <span className="text-xs text-ink-400">· {userName}</span>
            )}
          </div>
          <nav className="flex items-center">
            {tabs.map(t => (
              <NavLink
                key={t.path}
                to={t.path}
                end={t.path === '/'}
                className={({ isActive }) =>
                  `px-3.5 py-4 text-sm transition-colors ${
                    isActive
                      ? 'text-clay-500 border-b-2 border-clay-500'
                      : 'text-ink-500 hover:text-ink-900 border-b-2 border-transparent'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 py-2">
          <div className="flex items-center gap-2 text-xs text-ink-500">
            <span className="w-2 h-2 rounded-full bg-up-500"></span>
            <span>Claude Sonnet 4.6 · OAuth (Max)</span>
          </div>
          <div className="text-xs text-ink-500 font-mono">{now}</div>
        </div>
      </div>
    </header>
  );
}
