'use client';
import { Expand, Eye, EyeOff, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useRef, useState } from 'react';
import type { Finding } from '@/lib/types';
import { fieldLabel } from '@/lib/format';

function validBox(box: number[]): boolean { return box.length === 4 && box[2] > box[0] && box[3] > box[1]; }

export function EvidenceViewer({ imageUrl, findings, selectedRuleId, onSelect }: { imageUrl: string; findings: Finding[]; selectedRuleId?: string; onSelect?: (id: string) => void }) {
  const image = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState({ width: 1, height: 1 });
  const [boxes, setBoxes] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const visible = findings.filter((finding) => validBox(finding.bounding_box));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-500">{visible.length} localized evidence region{visible.length === 1 ? '' : 's'}</span>
        <div className="flex items-center gap-1">
          <button className="button-secondary !min-h-9 !px-2.5" onClick={() => setBoxes(!boxes)} aria-label="Toggle evidence boxes">{boxes ? <Eye size={15} /> : <EyeOff size={15} />}</button>
          <button className="button-secondary !min-h-9 !px-2.5" onClick={() => setZoom(Math.max(.5, zoom - .25))} aria-label="Zoom out"><ZoomOut size={15} /></button>
          <span className="min-w-12 text-center text-xs font-bold">{Math.round(zoom * 100)}%</span>
          <button className="button-secondary !min-h-9 !px-2.5" onClick={() => setZoom(Math.min(3, zoom + .25))} aria-label="Zoom in"><ZoomIn size={15} /></button>
          <button className="button-secondary !min-h-9 !px-2.5" onClick={() => setRotation((rotation + 90) % 360)} aria-label="Rotate view"><RotateCcw size={15} /></button>
          <a className="button-secondary !min-h-9 !px-2.5" href={imageUrl} target="_blank" rel="noreferrer" aria-label="Open full image"><Expand size={15} /></a>
        </div>
      </div>
      <div className="max-h-[680px] overflow-auto rounded-xl border bg-[linear-gradient(45deg,#eef2f1_25%,transparent_25%),linear-gradient(-45deg,#eef2f1_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#eef2f1_75%),linear-gradient(-45deg,transparent_75%,#eef2f1_75%)] bg-[length:18px_18px] p-3">
        <div className="relative mx-auto origin-top transition-transform" style={{ width: `${zoom * 100}%`, transform: `rotate(${rotation}deg)` }}>
          {/* Backend media cannot use next/image without a fixed allow-list. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img ref={image} src={imageUrl} alt="Uploaded package label with evidence regions" className="block h-auto w-full rounded-lg" onLoad={() => setNatural({ width: image.current?.naturalWidth || 1, height: image.current?.naturalHeight || 1 })} />
          {boxes && visible.map((finding) => {
            const [x1, y1, x2, y2] = finding.bounding_box;
            const selected = finding.rule_id === selectedRuleId;
            const tone = finding.status === 'FAIL' ? 'border-rose-600 bg-rose-500/20' : finding.status === 'UNCERTAIN' ? 'border-amber-500 bg-amber-400/20' : 'border-emerald-600 bg-emerald-500/15';
            return <button key={finding.rule_id} type="button" onClick={() => onSelect?.(finding.rule_id)} aria-label={`Show ${fieldLabel(finding.field)} finding`} className={`absolute border-2 ${tone} ${selected ? 'z-20 ring-4 ring-white/80' : 'z-10 hover:ring-2 hover:ring-white'}`} style={{ left: `${x1 / natural.width * 100}%`, top: `${y1 / natural.height * 100}%`, width: `${(x2 - x1) / natural.width * 100}%`, height: `${(y2 - y1) / natural.height * 100}%` }}><span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-navy px-1.5 py-0.5 text-[9px] font-bold text-white">{fieldLabel(finding.field)}</span></button>;
          })}
        </div>
      </div>
      {selectedRuleId && !visible.some((item) => item.rule_id === selectedRuleId) && <p className="notice mt-3 border-amber-200 bg-amber-50 text-amber-950">No trustworthy bounding box was available for this finding. LabelGuard does not fabricate evidence coordinates.</p>}
    </div>
  );
}
