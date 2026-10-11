import { useRef, useState } from "react";
import { Loader2, Plus, X, Undo2, History } from "lucide-react";
import { pageUrl } from "@/lib/api";
import { PC } from "@/constants/testIds";

const clamp = (v) => Math.max(0, Math.min(1000, v));

const PartEditor = ({ jobId, part, index, onChange, onRemove, onStart }) => {
  const ref = useRef(null);
  const startDrag = (edge) => (e) => {
    e.preventDefault();
    onStart();
    const rect = ref.current.getBoundingClientRect();
    const move = (ev) => {
      const v = clamp(Math.round(((ev.clientY - rect.top) / rect.height) * 1000));
      onChange(edge === "top" ? { ...part, y0: Math.min(v, part.y1 - 10) } : { ...part, y1: Math.max(v, part.y0 + 10) });
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const handle = "absolute left-0 right-0 h-3 -translate-y-1/2 cursor-ns-resize flex justify-center touch-none";
  return (
    <div className="space-y-1">
      <div className="flex justify-between font-mono text-[11px] text-[var(--pc-text2)]">
        <span>Page {part.page + 1} · {part.y0}–{part.y1}</span>
        {onRemove && <button data-testid={`crop-remove-part-${index}`} onClick={onRemove} className="hover:text-red-400 flex items-center gap-1"><X className="h-3 w-3" /> remove</button>}
      </div>
      <div ref={ref} data-testid={`crop-part-${index}`} className="relative select-none bg-white rounded overflow-hidden">
        <img src={pageUrl(jobId, part.page)} alt={`Page ${part.page + 1}`} className="w-full block pointer-events-none" draggable={false} />
        <div className="absolute inset-x-0 top-0 bg-black/55" style={{ height: `${part.y0 / 10}%` }} />
        <div className="absolute inset-x-0 bottom-0 bg-black/55" style={{ height: `${(1000 - part.y1) / 10}%` }} />
        <div className="absolute inset-x-0 border-2 border-[var(--pc-amber)] pointer-events-none" style={{ top: `${part.y0 / 10}%`, height: `${(part.y1 - part.y0) / 10}%` }} />
        <div data-testid={`crop-handle-top-${index}`} onPointerDown={startDrag("top")} className={handle} style={{ top: `${part.y0 / 10}%` }}><span className="w-16 h-3 rounded-full bg-[var(--pc-amber)]" /></div>
        <div data-testid={`crop-handle-bottom-${index}`} onPointerDown={startDrag("bottom")} className={handle} style={{ top: `${part.y1 / 10}%` }}><span className="w-16 h-3 rounded-full bg-[var(--pc-amber)]" /></div>
      </div>
    </div>
  );
};

export const CropEditor = ({ jobId, question, totalPages, onSave, onUndoSaved }) => {
  const [parts, setParts] = useState(question.parts);
  const [hist, setHist] = useState([]);
  const [saving, setSaving] = useState(false);
  const last = parts[parts.length - 1];
  const setPart = (i) => (p) => setParts((ps) => ps.map((x, j) => (j === i ? p : x)));
  const snap = () => setHist((h) => [...h.slice(-49), parts]);
  const change = (next) => { snap(); setParts(next); };
  const undo = () => { setParts(hist[hist.length - 1]); setHist((h) => h.slice(0, -1)); };
  const saved = question.crop_history?.length || 0;

  const save = async () => { setSaving(true); try { await onSave(parts); } finally { setSaving(false); } };
  const undoSaved = async () => { setSaving(true); try { await onUndoSaved(); } finally { setSaving(false); } };

  if (!parts.length) return <p className="text-sm text-[var(--pc-muted)]">This question has no stored crop regions (processed by an older version) — re-upload the PDF to adjust it.</p>;

  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--pc-text2)]">Drag the amber handles to move the top and bottom edges of the crop. Undo steps back through your changes before you save, and "Restore previous crop" goes back to the crop from before your last save.</p>
      {parts.map((p, i) => (
        <PartEditor key={`${p.page}-${i}`} jobId={jobId} part={p} index={i} onChange={setPart(i)} onStart={snap}
          onRemove={parts.length > 1 ? () => change(parts.filter((_, j) => j !== i)) : null} />
      ))}
      <div className="flex gap-3 flex-wrap sticky bottom-0 bg-[var(--pc-surface)] py-3">
        {last.page + 1 < totalPages && (
          <button data-testid={PC.cropAddPage} onClick={() => change([...parts, { page: last.page + 1, y0: 0, y1: 300 }])} className="pc-btn-secondary text-sm">
            <Plus className="h-4 w-4" /> Extend onto page {last.page + 2}
          </button>
        )}
        <button data-testid="crop-undo-button" onClick={undo} disabled={!hist.length || saving} className="pc-btn-secondary text-sm disabled:opacity-40">
          <Undo2 className="h-4 w-4" /> Undo{hist.length ? ` (${hist.length})` : ""}
        </button>
        <button data-testid={PC.cropSave} onClick={save} disabled={saving} className="pc-btn-primary text-sm">
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save & re-crop
        </button>
        {onUndoSaved && saved > 0 && (
          <button data-testid="crop-undo-saved-button" onClick={undoSaved} disabled={saving} title="Go back to the crop before your last save"
            className="pc-btn-secondary text-sm">
            <History className="h-4 w-4" /> Restore previous crop ({saved})
          </button>
        )}
      </div>
    </div>
  );
};
