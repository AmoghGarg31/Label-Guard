'use client';
import { Eye } from 'lucide-react';
import { confidence, fieldLabel, FINDING_LABELS } from '@/lib/format';
import type { ExtractedField, Finding } from '@/lib/types';

const tone = { PASS: 'bg-emerald-50 text-emerald-800 border-emerald-200', FAIL: 'bg-rose-50 text-rose-800 border-rose-200', UNCERTAIN: 'bg-amber-50 text-amber-900 border-amber-200' };
export function DeclarationCoverageMatrix({ extractedFields, findings, onHighlightRule }: { extractedFields: Record<string, ExtractedField>; findings: Finding[]; onHighlightRule?: (id: string) => void }) {
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Declaration</th><th>Detected text</th><th>Confidence</th><th>Rule & source</th><th>Result</th><th>Evidence</th></tr></thead><tbody>
    {findings.map((finding) => {
      const direct = extractedFields[finding.field];
      const responsible = ['manufacturer', 'packer', 'importer', 'marketer']
        .map((role) => [extractedFields[`${role}_name`]?.text, extractedFields[`${role}_address`]?.text].filter(Boolean).join(', '))
        .find(Boolean);
      const field = finding.field === 'responsible_party_name_and_address'
        ? { text: responsible ?? '', confidence: finding.confidence }
        : direct;
      const hasBox = finding.bounding_box?.[2] > finding.bounding_box?.[0] && finding.bounding_box?.[3] > finding.bounding_box?.[1];
      return <tr key={finding.rule_id}><td className="font-bold text-navy">{fieldLabel(finding.field)}</td><td className="max-w-xs break-words text-slate-700">{field?.text || <em className="text-slate-400">Not detected</em>}</td><td className="font-mono text-xs">{confidence(field?.confidence ?? finding.confidence)}</td><td><code className="text-xs font-bold text-teal-800">{finding.rule_id} v{finding.rule_version}</code><p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">{finding.source_citation}</p></td><td><span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${tone[finding.status]}`}>{FINDING_LABELS[finding.status]}</span></td><td>{hasBox && onHighlightRule ? <button className="button-secondary !min-h-8 !px-2 text-xs" onClick={() => onHighlightRule(finding.rule_id)}><Eye size={13} />View</button> : <span className="text-xs text-slate-400">Not localized</span>}</td></tr>;
    })}
  </tbody></table></div>;
}
