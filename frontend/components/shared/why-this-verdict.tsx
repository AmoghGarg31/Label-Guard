import { AlertCircle, CheckCircle2, HelpCircle, ShieldCheck } from 'lucide-react';
import { confidence, fieldLabel, STATUS_LABELS } from '@/lib/format';
import type { Finding, Inspection } from '@/lib/types';

export function WhyThisVerdict({ inspection }: { inspection: Inspection }) {
  const failed = inspection.findings.filter((item) => item.status === 'FAIL');
  const uncertain = inspection.findings.filter((item) => item.status === 'UNCERTAIN');
  const passed = inspection.findings.filter((item) => item.status === 'PASS');
  const qualityNeedsReview = inspection.quality.status !== 'good';
  const Icon = inspection.overall_status === 'compliant' ? CheckCircle2 : inspection.overall_status === 'potential_non_compliance' ? AlertCircle : HelpCircle;
  const summary = inspection.overall_status === 'compliant'
    ? `${passed.length} active checks passed. This means no configured issue was flagged; it is not legal certification.`
    : inspection.overall_status === 'potential_non_compliance'
      ? `${failed.length} active check${failed.length === 1 ? '' : 's'} failed deterministic presence or format criteria.`
      : uncertain.length
        ? `${uncertain.length} check${uncertain.length === 1 ? '' : 's'} could not be resolved from available evidence or applicability context.`
        : 'All active declaration checks passed, but the image-quality gate requires manual review.';
  return <div className="panel overflow-hidden">
    <div className="bg-navy p-5 text-white"><div className="flex items-start gap-3"><Icon className="mt-0.5 shrink-0 text-mint" /><div><p className="text-xs font-bold uppercase tracking-[.14em] text-slate-400">Why this result</p><h3 className="mt-1 text-xl font-black">{STATUS_LABELS[inspection.overall_status]}</h3><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{summary}</p></div></div></div>
    <div className="grid gap-4 p-5 lg:grid-cols-2">
      {[...failed, ...uncertain].map((finding) => <Reason key={finding.rule_id} finding={finding} />)}
      {failed.length === 0 && uncertain.length === 0 && <div className={`notice lg:col-span-2 ${qualityNeedsReview ? 'border-amber-200 bg-amber-50 text-amber-950' : 'border-emerald-200 bg-emerald-50 text-emerald-900'}`}><CheckCircle2 className="mr-2 inline" size={18} />Every active rule returned PASS at its configured confidence threshold.{qualityNeedsReview ? ' Capture quality still prevents an automated clear result.' : ''}</div>}
    </div>
    <div className="border-t bg-slate-50 px-5 py-3 text-xs leading-5 text-slate-600"><ShieldCheck className="mr-1.5 inline text-teal-700" size={15} />Verdict source: backend deterministic rule engine <strong>{inspection.rule_engine_version}</strong>. Gemini reads the image, but deterministic validators accept evidence and no generative model decides PASS, FAIL, UNCERTAIN, or the overall result.</div>
  </div>;
}

function Reason({ finding }: { finding: Finding }) {
  return <div className={`rounded-xl border p-4 ${finding.status === 'FAIL' ? 'border-rose-200 bg-rose-50' : 'border-amber-200 bg-amber-50'}`}><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm text-navy">{fieldLabel(finding.field)}</strong><code className="text-[10px] font-bold text-slate-600">{finding.rule_id}</code></div><p className="mt-2 text-sm leading-6 text-slate-700">{finding.description}</p><p className="mt-2 text-xs text-slate-500">Evidence confidence {confidence(finding.confidence)} · {finding.applicability === 'unknown' ? 'applicability unresolved' : 'rule applicable'}</p></div>;
}
