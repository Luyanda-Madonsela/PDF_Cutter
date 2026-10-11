import { useEffect, useState } from "react";
import { Eraser, Loader2, Undo2 } from "lucide-react";
import { getErase, pageUrl } from "@/lib/api";

const key = (b) => b.join(",");

const PageBoxes = ({ jobId, page, part, boxes, selected, onToggle }) => (
  <div className="space-y-1">
    <p className="font-mono text-[11px] text-[var(--pc-text2)]">Page {page + 1} — click a box to include / exclude it</p>
    <div className="relative bg-white rounded overflow-hidden select-none">
      <img src={pageUrl(jobId, page)} alt={`Page ${page + 1}`} className="w-full block" draggable={false} />
      {part && <div className="absolute inset-x-0 border-y-2 border-dashed border-sky-400 pointer-events-none" style={{ top: `${part.y0 / 10}%`, height: `${(part.y1 - part.y0) / 10}%` }} />}
      {boxes.map((b) => {
        const on = selected.has(key(b));
        const [, y0, x0, y1, x1] = b;
        return (
          <button key={key(b)} data-testid={`erase-box-${key(b)}`} onClick={() => onToggle(b)} title={on ? "Will be erased" : "Will be kept"}
            className={`absolute border-2 transition-colors ${on ? "border-red-500 bg-red-500/30" : "border-slate-400 border-dashed bg-transparent"}`}
            style={{ top: `${y0 / 10 - 0.3}%`, left: `${x0 / 10 - 0.4}%`, height: `${(y1 - y0) / 10 + 0.6}%`, width: `${(x1 - x0) / 10 + 0.8}%` }} />
        );
      })}
    </div>
  </div>
);

export const EraseReview = ({ doc, q, onDecide }) => {
  const [info, setInfo] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getErase(doc.id, q.id).then((d) => {
      setInfo(d);
      setSelected(new Set((d.status === "pending" ? d.proposals : d.applied).map(key)));
    });
  }, [doc.id, q.id, q.storage_path]);

  if (!info) return <Loader2 className="h-5 w-5 animate-spin text-[var(--pc-amber)]" />;
  if (!info.proposals.length) return <p className="text-sm text-[var(--pc-muted)]">The AI did not suggest anything to erase in this question.</p>;
  const toggle = (b) => setSelected((s) => { const n = new Set(s); n.has(key(b)) ? n.delete(key(b)) : n.add(key(b)); return n; });
  const decide = async (boxes) => { setBusy(true); try { await onDecide(boxes); } finally { setBusy(false); } };
  const pages = [...new Set(info.proposals.map((b) => b[0]))];

  return (
    <div data-testid="erase-review" className="space-y-4">
      <p className="text-xs text-[var(--pc-text2)]">
        The AI suggests erasing the <span className="text-red-400">red boxes</span> (question numbers, headings, totals). Nothing is erased until you approve.
        Status: <span data-testid="erase-status" className="font-mono text-[var(--pc-amber)]">{info.status}</span>
      </p>
      <div className="max-h-[50vh] overflow-auto space-y-4">
        {pages.map((p) => (
          <PageBoxes key={p} jobId={doc.id} page={p} part={q.parts.find((x) => x.page === p)} boxes={info.proposals.filter((b) => b[0] === p)} selected={selected} onToggle={toggle} />
        ))}
      </div>
      <div className="flex gap-3 flex-wrap sticky bottom-0 bg-[var(--pc-surface)] py-2">
        <button data-testid="erase-apply-button" disabled={busy || !selected.size} onClick={() => decide(info.proposals.filter((b) => selected.has(key(b))))} className="pc-btn-primary text-sm">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eraser className="h-4 w-4" />} Approve erase ({selected.size})
        </button>
        <button data-testid="erase-keep-button" disabled={busy} onClick={() => decide([])} className="pc-btn-secondary text-sm">
          <Undo2 className="h-4 w-4" /> Keep original
        </button>
      </div>
    </div>
  );
};
