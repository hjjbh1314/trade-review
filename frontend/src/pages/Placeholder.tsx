export function Placeholder({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <h1 className="text-xl font-semibold text-ink-900 mb-1">{title}</h1>
      <p className="text-sm text-ink-500 mb-8">{hint}</p>
      <div className="bg-white border border-cream-300 rounded-xl p-12 text-center text-ink-400 text-sm">
        此页功能在后续阶段实现，详见 DESIGN.md 的分阶段计划。
      </div>
    </div>
  );
}
