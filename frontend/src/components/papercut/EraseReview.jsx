import { useEffect, useState } from "react";
import { Eraser, Loader2, Undo2 } from "lucide-react";
import { getErase } from "@/lib/api";
import { ErasePage, boxKey } from "./ErasePage";

export const EraseReview = ({ doc, q, onDecide }) => {
  const [info, setInfo] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [manual, setManual] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getErase(doc.id, q.id).then((d) => {
      setInfo(d);
      setSelected(new Set((d.status === "pending" ? d.proposals : d.applied).map(boxKey)));
      setManual(d.manual || []);
    });
  }, [doc.id, q.id, q.storage_path]);

  if (!info) return <Loader2 className="h-5 w-5 animate-spin text-[var(--pc-amber)]" />;
  const toggle = (b) => setSelected((s) => { const n = new Set(s); n.has(boxKey(b)) ? n.delete(boxKey(b)) : n.add(boxKey(b)); return n; });
  const chosen = info.proposals.filter((b) => selected.has(boxKey(b)));
  const decide = async (boxes, man) => { setBusy(true); try { await onDecide(boxes, man); } finally { setBusy(false); } };
  const pages = [...new Set([...info.pages, ...info.proposals.map((b) => b[0])])].sort((a, b) => a - b);
  const total = chosen.length + manual.length;

  return (
    <div data-testid="erase-review" className="space-y-4">
      <p className="text-xs text-[var(--pc-text2)]">
        {info.proposals.length > 0
          ? <>The AI suggests erasing the <span className="text-red-400">red boxes</span> (question numbers, headings, totals). </>
          : <>The AI did not suggest anything to erase. </>}
        Drag on the page to add your own <span className="text-[var(--pc-amber)]">amber areas</span>. Nothing is erased until you approve.
        {" "}Status: <span data-testid="erase-status" className="font-mono text-[var(--pc-amber)]">{info.status}</span>
      </p>
      <div className="max-h-[50vh] overflow-auto space-y-4">
        {pages.map((p) => (
          <ErasePage key={p} jobId={doc.id} page={p} parts={q.parts.filter((x) => x.page === p)}
            proposals={info.proposals.filter((b) => b[0] === p)} selected={selected} onToggle={toggle}
            manual={manual.map((b, i) => ({ b, i })).filter(({ b }) => b[0] === p)}
            onAdd={(b) => setManual((m) => [...m, b])}
            onUpdate={(i, b) => setManual((m) => m.map((x, j) => (j === i ? b : x)))}
            onRemove={(i) => setManual((m) => m.filter((_, j) => j !== i))} />
        ))}
      </div>
      <div className="flex gap-3 flex-wrap items-center sticky bottom-0 bg-[var(--pc-surface)] py-2">
        <button data-testid="erase-apply-button" disabled={busy || !total} onClick={() => decide(chosen, manual)} className="pc-btn-primary text-sm">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eraser className="h-4 w-4" />} Approve erase ({total})
        </button>
        <button data-testid="erase-keep-button" disabled={busy} onClick={() => decide([], [])} className="pc-btn-secondary text-sm">
          <Undo2 className="h-4 w-4" /> Keep original
        </button>
        {manual.length > 0 && <span data-testid="erase-manual-count" className="font-mono text-xs text-[var(--pc-amber)]">{manual.length} drawn by you</span>}
      </div>
    </div>
  );
};
