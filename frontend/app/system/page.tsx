'use client';
import { CheckCircle2, Database, Scale, ShieldAlert, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { ErrorState } from '@/components/shared/error-state';
import { LoadingState } from '@/components/shared/loading-state';
import { API_BASE_URL, getSystemStatus } from '@/lib/api-client';
import type { SystemStatus } from '@/lib/types';

export default function SystemPage() {
  const [data, setData] = useState<SystemStatus>(); const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getSystemStatus().then(setData).catch((reason: Error) => setError(reason.message)); }, []); useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />; if (!data) return <LoadingState message="Checking Gemini extraction, request routing, rate limits, and deterministic rules…" />;
  const rate = data.gemini.rate_limit;
  return <div className="animate-enter"><div className="page-header"><div><p className="eyebrow">Runtime diagnostics</p><h1 className="page-title">System status</h1><p className="page-copy">Direct readiness checks from the backend at <code>{API_BASE_URL}</code>.</p></div><span className={`rounded-full px-3 py-1.5 text-sm font-black ${data.status === 'ok' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`}>{data.status.toUpperCase()}</span></div>
    <div className="grid gap-5 xl:grid-cols-3">
      <Diagnostic icon={<Database />} title="Inspection database" ready={data.database.available} rows={[["Saved records", String(data.database.inspection_count ?? '—')], ['Path', data.database.path ?? 'Not disclosed']]} />
      <Diagnostic icon={<Sparkles />} title="Gemini-only extraction" ready={data.extraction.available} rows={[["Mode", data.extraction.mode.replaceAll('_', ' ')], ['Fast model', data.gemini.fast_model ?? data.gemini.model], ['Quality model', data.gemini.quality_model ?? data.gemini.model], ['Fallback route', data.gemini.fallback_models?.join(' → ') || 'none'], ['Request limit', rate ? `${rate.limit_per_minute}/minute · ${rate.max_concurrent_requests} concurrent` : 'not reported'], ['Transient attempts', rate ? String(rate.max_attempts_per_model ?? 1) : '—'], ['Window remaining', rate ? String(rate.remaining_in_current_window) : '—'], ['Last safe error', data.gemini.last_error ?? 'none']]} />
      <Diagnostic icon={<Scale />} title="Rule engine" ready={data.rule_engine.available} rows={[["Version", data.rule_engine.version], ['Active rules', String(data.rule_engine.active_rule_count)], ['Verdict source', data.rule_engine.verdict_source.replaceAll('_', ' ')]]} />
    </div>
    <div className="notice mt-6 border-teal-200 bg-teal-50 text-teal-950"><ShieldAlert className="mr-2 inline" size={18} /><strong>Integrity boundary:</strong> Gemini is the only image reader. Deterministic field validators decide which candidates become evidence, and only the versioned backend rule engine assigns PASS, FAIL, UNCERTAIN and the overall automated result.</div>
    {data.gemini.enabled && <div className="notice mt-3 border-blue-200 bg-blue-50 text-blue-950">{data.gemini.external_processing_disclosure}</div>}
  </div>;
}
function Diagnostic({ icon, title, ready, rows }: { icon: React.ReactNode; title: string; ready: boolean; rows: string[][] }) { return <section className="panel overflow-hidden"><div className="panel-head"><div className="flex items-center gap-2 text-navy">{icon}<h2 className="section-title">{title}</h2></div>{ready ? <CheckCircle2 className="text-emerald-600" /> : <ShieldAlert className="text-amber-600" />}</div><dl className="panel-body space-y-3">{rows.map(([key, value]) => <div key={key} className="border-b border-slate-100 pb-3 last:border-0 last:pb-0"><dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{key}</dt><dd className="mt-1 break-all text-sm font-semibold capitalize text-slate-700">{value}</dd></div>)}</dl></section>; }
