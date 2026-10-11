import { useState } from "react";
import { toast } from "sonner";
import { CropEditor } from "./CropEditor";
import { EraseReview } from "./EraseReview";
import { imageUrl, updateQuestion, decideErase } from "@/lib/api";

const MODES = [["image", "Image"], ["erase", "Erase"], ["adjust", "Adjust crop"]];

export const LinkedEditor = ({ refItem, documents, onSetChange, kind }) => {
  const [mode, setMode] = useState("image");
  const doc = documents.find((d) => d.id === refItem.job_id);
  const q = doc?.questions.find((x) => x.id === refItem.qid);
  if (!q) return null;
  const act = async (fn, msg) => {
    try { onSetChange(await fn()); toast.success(msg); setMode("image"); }
    catch (e) { toast.error(e.response?.data?.detail || "Action failed"); }
  };
  const tid = `linked-${kind}-${q.id}`;
  return (
    <div data-testid={tid} className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-mono text-[var(--pc-muted)] mr-auto">{q.filename}{q.erase_status === "pending" ? " · erase needs approval" : ""}</span>
        {MODES.map(([k, l]) => (
          <button key={k} data-testid={`${tid}-${k}`} onClick={() => setMode(k)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${mode === k ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-text2)] border border-[var(--pc-border)] hover:text-[var(--pc-text)]"}`}>{l}</button>
        ))}
      </div>
      {mode === "image" && <div className="rounded-md bg-white"><img src={`${imageUrl(doc.id, q.id)}?v=${q.storage_path.slice(-12)}`} alt={q.label} className="w-full" /></div>}
      {mode === "erase" && (
        <EraseReview doc={doc} q={q} onDecide={(boxes, manual) => act(() => decideErase(doc.id, q.id, boxes, manual), boxes.length + manual.length ? "Erase applied" : "Original kept")} />
      )}
      {mode === "adjust" && (
        <CropEditor key={q.storage_path} jobId={doc.id} question={q} totalPages={doc.total_pages}
          onSave={(parts) => act(() => updateQuestion(doc.id, q.id, { parts }), "Crop updated")} />
      )}
    </div>
  );
};

export const LinkedList = ({ refs, ...rest }) => (
  <div className="space-y-6 max-h-[60vh] overflow-auto">
    {refs.map((r) => (
      <div key={r.qid}>
        {r.label && <p className="text-xs font-mono text-[var(--pc-muted)] mb-1">For Q{r.label}</p>}
        <LinkedEditor refItem={r} {...rest} />
      </div>
    ))}
  </div>
);
