import { useRef } from "react";
import { Loader2, RotateCw, Trash2, Plus, AlertTriangle, CheckCircle2 } from "lucide-react";
import { DOC_LABEL, ACTIVE_DOC } from "@/lib/api";

const DocRow = ({ d, onRetry, onDelete }) => {
  const active = ACTIVE_DOC.includes(d.status);
  const statusText = d.status === "processing" ? `AI reading pages ${d.pages_done}/${d.total_pages || "?"}`
    : d.status === "waiting" ? "Waiting for the rest of the set" : d.status === "classifying" ? "Reading cover"
    : d.status === "paused" ? `Paused: ${d.error || "spending limit reached"}` : d.status;
  return (
    <li data-testid={`doc-row-${d.id}`} className="flex items-center gap-3 py-2">
      {d.status === "done" ? <CheckCircle2 className="h-4 w-4 text-[var(--pc-emerald)] shrink-0" />
        : d.status === "error" ? <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
          : <Loader2 className={`h-4 w-4 text-[var(--pc-amber)] shrink-0 ${active && d.status !== "waiting" ? "animate-spin" : ""}`} />}
      <span className="w-28 shrink-0 text-xs font-mono uppercase tracking-wider text-[var(--pc-text2)]">{DOC_LABEL[d.meta.doc_type]}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm truncate">{d.filename}</p>
        <p className={`text-[11px] font-mono ${d.status === "error" ? "text-red-400" : "text-[var(--pc-muted)]"}`}>
          {d.status === "error" ? d.error : d.status === "done" ? `${d.questions.length} images · ${d.total_pages}p` : statusText}
        </p>
      </div>
      {d.status === "error" && <button data-testid={`doc-retry-${d.id}`} onClick={() => onRetry(d.id)} className="p-1.5 text-[var(--pc-text2)] hover:text-[var(--pc-amber)]"><RotateCw className="h-4 w-4" /></button>}
      <button data-testid={`doc-delete-${d.id}`} onClick={() => onDelete(d.id)} className="p-1.5 text-[var(--pc-muted)] hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
    </li>
  );
};

const AddDoc = ({ type, label, onAdd, urgent }) => {
  const ref = useRef(null);
  return (
    <>
      <input ref={ref} data-testid={`add-${type}-input`} type="file" accept=".pdf,application/pdf" multiple={type === "addendum" || type === "errata"} className="hidden"
        onChange={(e) => { const fs = Array.from(e.target.files || []); e.target.value = ""; fs.length && onAdd(type, fs); }} />
      <button data-testid={`add-${type}-button`} onClick={() => ref.current?.click()} className={`pc-btn-secondary !px-3 !py-1.5 text-xs ${urgent ? "!border-red-400/60 !text-red-300" : ""}`}>
        <Plus className="h-3.5 w-3.5" /> {label}
      </button>
    </>
  );
};

export const DocumentsPanel = ({ set, onRetry, onDelete, onAdd }) => {
  const types = new Set(set.documents.map((d) => d.meta.doc_type));
  return (
    <div data-testid="documents-panel" className="pt-4 border-t border-[var(--pc-border)]">
      {set.status === "paused" && <p data-testid="budget-paused-warning" className="mb-3 text-sm text-[var(--pc-amber)]">Paused because the monthly AI spending limit was reached. It resumes when you raise the limit (AI settings, Usage & cost) or next month.</p>}
      {set.status === "needs_memo" && <p data-testid="needs-memo-warning" className="mb-3 text-sm text-red-300">This paper has no memo yet — it won't be split until you add one.</p>}
      {set.status === "needs_paper" && <p data-testid="needs-paper-warning" className="mb-3 text-sm text-red-300">No question paper in this set yet — add it to start splitting.</p>}
      <ul className="divide-y divide-[var(--pc-border)]">
        {set.documents.map((d) => <DocRow key={d.id} d={d} onRetry={onRetry} onDelete={onDelete} />)}
      </ul>
      <div className="flex flex-wrap gap-2 mt-3">
        {!types.has("question_paper") && <AddDoc type="question_paper" label="Question paper" onAdd={onAdd} urgent />}
        {!types.has("memo") && <AddDoc type="memo" label="Memo" onAdd={onAdd} urgent />}
        <AddDoc type="addendum" label="Addendum" onAdd={onAdd} />
        <AddDoc type="errata" label="Errata" onAdd={onAdd} />
      </div>
    </div>
  );
};
