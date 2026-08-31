'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { getAnalytics } from '@/lib/api-client';
import type { Analytics } from '@/lib/types';

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics>(); const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getAnalytics().then(setData).catch((reason: Error) => setError(reason.message)); }, []); useEffect(load, [load]);
  const maximum = useMemo(() => Math.max(1, ...(data?.daily_counts.map((item) => item.count) ?? [1])), [data]);
  if (error) return <ErrorState message={error} onRetry={load} />; if (!data) return <LoadingState />;
  const status = data.status_counts;
  return <div className="animate-enter"><div className="page-header"><div><p className="eyebrow">Operational insight</p><h1 className="page-title">Inspection analytics</h1><p className="page-copy">A descriptive view of saved backend results. Counts do not measure market-wide compliance and are not predictive.</p></div></div>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Saved inspections" value={data.total_inspections} /><Metric label="No issue flagged" value={status.compliant ?? 0} tone="green" /><Metric label="Potential issues" value={status.potential_non_compliance ?? 0} tone="rose" /><Metric label="Manual review" value={status.manual_review_required ?? 0} tone="amber" /></section>
    <section className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_.6fr]"><div className="panel"><div className="panel-head"><h2 className="section-title">Activity · last 14 recorded days</h2></div><div className="panel-body"><div className="flex h-64 items-end gap-2 border-b border-slate-200 px-2 pt-6">{data.daily_counts.length ? data.daily_counts.map((item) => <div key={item.date} className="group flex h-full min-w-0 flex-1 flex-col justify-end"><span className="mb-1 text-center text-[10px] font-bold text-slate-500">{item.count}</span><div className="min-h-1 rounded-t bg-teal-700 transition group-hover:bg-mint" style={{ height: `${Math.max(4, item.count / maximum * 90)}%` }} /><span className="mt-2 -rotate-45 truncate text-[9px] text-slate-400">{item.date.slice(5)}</span></div>) : <p className="m-auto text-sm text-slate-500">No activity recorded.</p>}</div></div></div><div className="panel"><div className="panel-head"><h2 className="section-title">Inspector review states</h2></div><div className="panel-body space-y-4">{Object.entries(data.review_counts).map(([name, count]) => <Bar key={name} name={name.replaceAll('_', ' ')} value={count} total={data.total_inspections} />)}{!Object.keys(data.review_counts).length && <p className="text-sm text-slate-500">No review states recorded.</p>}</div></div></section>
    <p className="mt-4 text-xs text-slate-500">Dataset window: {data.is_complete_history ? 'all saved inspections' : `latest ${data.sample_limit} inspections`}.</p>
  </div>;
}
function Metric({ label, value, tone = 'blue' }: { label: string; value: number; tone?: 'blue' | 'green' | 'rose' | 'amber' }) { const colors = { blue: 'bg-teal-600', green: 'bg-emerald-500', rose: 'bg-rose-600', amber: 'bg-amber-500' }; return <div className="metric"><span className={`absolute inset-x-0 top-0 h-1 ${colors[tone]}`} /><p className="metric-label">{label}</p><p className="metric-value">{value}</p></div>; }
function Bar({ name, value, total }: { name: string; value: number; total: number }) { return <div><div className="mb-1 flex justify-between gap-3 text-xs"><span className="capitalize text-slate-600">{name.toLowerCase()}</span><strong>{value}</strong></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-teal-700" style={{ width: `${total ? value / total * 100 : 0}%` }} /></div></div>; }
