import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type Time,
} from 'lightweight-charts';
import type { Market, TradeRecord } from '../api';
import { fetchKLine, listTrades } from '../api';

type Period = 'daily' | 'weekly' | 'monthly';

export function KLineChart({ symbol, market, name }: {
  symbol: string;
  market: Market;
  name?: string | null;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [period, setPeriod] = useState<Period>('daily');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastClose, setLastClose] = useState<number | null>(null);
  const [dailyChg, setDailyChg] = useState<number | null>(null);

  useEffect(() => {
    if (!boxRef.current) return;
    const container = boxRef.current;

    const chart = createChart(container, {
      layout: {
        background: { color: '#FFFFFF' },
        textColor: '#6B6855',
        fontFamily: '-apple-system, BlinkMacSystemFont, PingFang SC, sans-serif',
      },
      grid: {
        vertLines: { color: '#EFECE2' },
        horzLines: { color: '#EFECE2' },
      },
      rightPriceScale: { borderColor: '#E3DFD1' },
      timeScale: { borderColor: '#E3DFD1', timeVisible: false },
      crosshair: { mode: 1 },
      width: container.clientWidth,
      height: 380,
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor:      '#2D8659',
      downColor:    '#C14D3F',
      borderUpColor:   '#2D8659',
      borderDownColor: '#C14D3F',
      wickUpColor:   '#2D8659',
      wickDownColor: '#C14D3F',
    });
    const ma5Line  = chart.addSeries(LineSeries, { color: '#D97757', lineWidth: 1, title: 'MA5',  priceLineVisible: false });
    const ma20Line = chart.addSeries(LineSeries, { color: '#6B7FB8', lineWidth: 1, title: 'MA20', priceLineVisible: false });
    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#C9C4B2', priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    let disposed = false;

    async function load() {
      setLoading(true);
      setErr(null);
      try {
        const [k, trades] = await Promise.all([
          fetchKLine(symbol, market, period, 180),
          listTrades(symbol, 100).catch(() => [] as TradeRecord[]),
        ]);
        if (disposed) return;

        candle.setData(
          k.bars.map(b => ({
            time: b.time as Time,
            open: b.open, high: b.high, low: b.low, close: b.close,
          })),
        );
        ma5Line.setData(k.ma5.map(p => ({ time: p.time as Time, value: p.value })));
        ma20Line.setData(k.ma20.map(p => ({ time: p.time as Time, value: p.value })));
        volSeries.setData(
          k.bars.map(b => ({
            time: b.time as Time,
            value: b.volume,
            color: b.close >= b.open ? 'rgba(45,134,89,0.35)' : 'rgba(193,77,63,0.35)',
          })),
        );

        if (k.bars.length > 0) {
          const last = k.bars[k.bars.length - 1];
          setLastClose(last.close);
          setDailyChg(last.open > 0 ? ((last.close - last.open) / last.open) * 100 : null);
        }

        // 买卖点标记（用前一版本的 createSeriesMarkers API 已不兼容 v5；
        // 简化为在蜡烛上添加 priceLine）
        const buyLines: Array<ReturnType<typeof candle.createPriceLine>> = [];
        for (const t of trades) {
          buyLines.push(candle.createPriceLine({
            price: t.price,
            color: t.action === 'buy' ? '#2D8659' : '#C14D3F',
            lineWidth: 1,
            lineStyle: 2, // dashed
            axisLabelVisible: true,
            title: `${t.action === 'buy' ? 'B' : 'S'} ${t.trade_time.slice(5, 10)}`,
          }));
        }

        chart.timeScale().fitContent();
      } catch (e) {
        if (!disposed) setErr(String(e));
      } finally {
        if (!disposed) setLoading(false);
      }
    }

    load();

    const onResize = () => {
      if (boxRef.current) chart.applyOptions({ width: boxRef.current.clientWidth });
    };
    window.addEventListener('resize', onResize);

    return () => {
      disposed = true;
      window.removeEventListener('resize', onResize);
      chart.remove();
    };
  }, [symbol, market, period]);

  return (
    <div className="bg-white border border-cream-300 rounded-xl">
      <div className="flex items-center justify-between px-5 py-3 border-b border-cream-300">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-ink-900">
            {name ?? symbol} <span className="text-ink-400 font-normal text-sm">{symbol}</span>
          </h2>
          {lastClose !== null && (
            <span className={`text-sm font-mono ${(dailyChg ?? 0) >= 0 ? 'text-up-500' : 'text-down-500'}`}>
              {lastClose.toFixed(2)} {dailyChg != null ? `(${dailyChg >= 0 ? '+' : ''}${dailyChg.toFixed(2)}%)` : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 text-xs">
          {(['daily', 'weekly', 'monthly'] as const).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
                    className={`px-2 py-1 rounded ${period === p
                        ? 'bg-clay-500 text-white font-medium'
                        : 'border border-cream-300 text-ink-700 hover:bg-cream-100'}`}>
              {p === 'daily' ? '日K' : p === 'weekly' ? '周K' : '月K'}
            </button>
          ))}
        </div>
      </div>
      {err && <div className="px-5 py-2 text-xs text-down-500 bg-down-100">{err}</div>}
      {loading && !err && (
        <div className="px-5 py-2 text-xs text-ink-400">加载中...</div>
      )}
      <div ref={boxRef} style={{ width: '100%', height: 380 }} />
    </div>
  );
}
