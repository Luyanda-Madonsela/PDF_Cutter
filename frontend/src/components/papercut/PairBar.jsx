import { useRef } from "react";
import { BookCheck, Loader2, Upload, ArrowRight } from "lucide-react";
import { PC } from "@/constants/testIds";

export const PairBar = ({ job, onAttach, onOpen }) => {
  const inputRef = useRef(null);
  const p = job.paired;
  const isMemo = job.meta?.doc_type === "memo";
  const matched = Object.keys(job.pair_map || {}).length;

  if (p) {
    const busy = p.status !== "done";
    return (
      <div data-testid={PC.memoStatus} className="flex items-center gap-3 flex-wrap text-sm">
        {busy ? <Loader2 className="h-4 w-4 animate-spin text-[var(--pc-amber)]" /> : <BookCheck className="h-4 w-4 text-[var(--pc-emerald)]" />}
        <span className="text-[var(--pc-text2)]">
          {isMemo ? "Memo for" : "Memo"} <span className="font-mono text-[var(--pc-text)]">{p.base_name || p.filename}</span>
          {busy ? ` — ${p.status} ${p.pages_done}/${p.total_pages || "?"}p` : ` — ${matched}/${job.questions.length} matched`}
        </span>
        <button data-testid={PC.openPartnerButton} onClick={() => onOpen(p.job_id)} className="inline-flex items-center gap-1 text-xs font-mono text-[var(--pc-amber)] hover:underline">open <ArrowRight className="h-3 w-3" /></button>
      </div>
    );
  }
  if (isMemo) return <p data-testid={PC.memoStatus} className="text-sm text-[var(--pc-muted)]">Not yet matched to a question paper.</p>;
  return (
    <div data-testid={PC.memoStatus} className="flex items-center gap-3 flex-wrap text-sm">
      <span className="text-[var(--pc-muted)]">No memo matched yet.</span>
      <input ref={inputRef} data-testid={PC.attachMemoInput} type="file" accept=".pdf,application/pdf" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; f && onAttach(f); }} />
      <button data-testid={PC.attachMemoButton} onClick={() => inputRef.current?.click()} className="pc-btn-secondary !py-1.5 text-xs">
        <Upload className="h-3.5 w-3.5" /> Attach memo PDF
      </button>
    </div>
  );
};
