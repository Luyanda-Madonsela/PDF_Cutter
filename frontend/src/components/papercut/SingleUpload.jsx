import { useRef, useState } from "react";
import { FileText, Loader2, Plus, X } from "lucide-react";

const Slot = ({ id, title, hint, required, multiple, files, onChange }) => {
  const ref = useRef(null);
  const add = (list) => {
    const pdfs = Array.from(list || []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    onChange(multiple ? [...files, ...pdfs] : pdfs.slice(0, 1));
  };
  return (
    <div data-testid={`slot-${id}`} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); add(e.dataTransfer.files); }}
      className={`rounded-lg border-2 border-dashed p-4 transition-colors duration-200 ${files.length ? "border-[var(--pc-emerald)]/60 bg-[var(--pc-emerald)]/5" : "border-[var(--pc-border)] hover:border-[var(--pc-text2)]"}`}>
      <input ref={ref} data-testid={`slot-${id}-input`} type="file" accept=".pdf,application/pdf" multiple={multiple} className="hidden"
        onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-heading font-bold">{title} {required ? <span className="text-[var(--pc-amber)]">*</span> : <span className="text-xs font-mono text-[var(--pc-muted)]">optional</span>}</p>
          <p className="text-xs text-[var(--pc-text2)] mt-0.5">{hint}</p>
        </div>
        {(multiple || !files.length) && (
          <button data-testid={`slot-${id}-add`} onClick={() => ref.current?.click()} className="pc-btn-secondary !px-3 !py-1.5 text-xs shrink-0"><Plus className="h-3.5 w-3.5" /> PDF</button>
        )}
      </div>
      <ul className="mt-3 space-y-1">
        {files.map((f, i) => (
          <li key={`${f.name}-${i}`} className="flex items-center gap-2 text-xs font-mono">
            <FileText className="h-3.5 w-3.5 text-[var(--pc-emerald)] shrink-0" /><span className="truncate flex-1">{f.name}</span>
            <button data-testid={`slot-${id}-remove-${i}`} onClick={() => onChange(files.filter((_, j) => j !== i))} className="hover:text-red-400"><X className="h-3.5 w-3.5" /></button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export const SingleUpload = ({ onSubmit }) => {
  const [qp, setQp] = useState([]);
  const [memo, setMemo] = useState([]);
  const [addenda, setAddenda] = useState([]);
  const [errata, setErrata] = useState([]);
  const [busy, setBusy] = useState(false);
  const ready = qp.length === 1 && memo.length === 1;

  const submit = async () => {
    setBusy(true);
    const ok = await onSubmit({ qp: qp[0], memo: memo[0], addenda, errata });
    setBusy(false);
    if (ok) { setQp([]); setMemo([]); setAddenda([]); setErrata([]); }
  };

  return (
    <div data-testid="single-upload-panel" className="pc-card p-6 sm:p-8 pc-rise">
      <div className="pc-overline mb-4">One paper — upload the full set together</div>
      <div className="grid sm:grid-cols-2 gap-4">
        <Slot id="qp" title="Question paper" hint="The exam paper itself" required files={qp} onChange={setQp} />
        <Slot id="memo" title="Memo" hint="Marking guideline for this paper" required files={memo} onChange={setMemo} />
        <Slot id="addendum" title="Addenda" hint="Graphs, diagrams, sources used by questions" multiple files={addenda} onChange={setAddenda} />
        <Slot id="errata" title="Errata" hint="Correction notices for this paper" multiple files={errata} onChange={setErrata} />
      </div>
      <div className="mt-6 flex items-center gap-4 flex-wrap">
        <button data-testid="single-submit-button" disabled={!ready || busy} onClick={submit} className="pc-btn-primary">
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Split this paper
        </button>
        {!ready && <span className="text-xs text-[var(--pc-muted)]">A question paper and its memo are both required.</span>}
      </div>
    </div>
  );
};
