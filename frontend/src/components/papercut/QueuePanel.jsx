import { useState } from "react";
import { Download, Trash2, RotateCw, Link2 } from "lucide-react";
import { zipUrl } from "@/lib/api";
import { PC } from "@/constants/testIds";

const statusColor = { done: "text-[var(--pc-emerald)]", error: "text-red-400", processing: "text-[var(--pc-amber)]", queued: "text-[var(--pc-muted)]" };
const FILTERS = [["all", "All"], ["active", "Active"], ["done", "Done"], ["error", "Failed"]];

const matches = (j, f) => f === "all" || (f === "active" ? ["queued", "processing"].includes(j.status) : j.status === f);

const QueueItem = ({ j, active, onSelect, onDelete, onRetry }) => (
  <li className={`group flex items-center gap-2 px-2 py-2 rounded-md transition-colors duration-150 ${active ? "bg-[var(--pc-surface2)]" : "hover:bg-[var(--pc-surface2)]/60"}`}>
    <button data-testid={`history-item-${j.id}`} onClick={() => onSelect(j.id)} className="flex-1 min-w-0 text-left">
      <p className="text-sm truncate flex items-center gap-1.5">
        {j.meta?.doc_type === "memo" && <span className="text-[10px] font-mono px-1 rounded bg-[var(--pc-emerald)]/15 text-[var(--pc-emerald)]">MEMO</span>}
        {j.paired_job_id && <Link2 className="h-3 w-3 text-[var(--pc-amber)] shrink-0" />}
        <span className="truncate">{j.base_name || j.filename}</span>
      </p>
      <p className={`font-mono text-[11px] ${statusColor[j.status]}`}>
        {j.status}{j.status === "processing" && j.total_pages ? ` ${j.pages_done}/${j.total_pages}p` : j.total_pages ? ` · ${j.total_pages}p` : ""}
      </p>
    </button>
    {j.status === "done" && <a data-testid={`history-redownload-btn-${j.id}`} href={zipUrl(j.id)} className="p-1.5 rounded text-[var(--pc-text2)] hover:text-[var(--pc-amber)]"><Download className="h-4 w-4" /></a>}
    {j.status === "error" && <button data-testid={`history-retry-btn-${j.id}`} onClick={() => onRetry(j.id)} className="p-1.5 rounded text-[var(--pc-text2)] hover:text-[var(--pc-amber)]"><RotateCw className="h-4 w-4" /></button>}
    <button data-testid={`history-delete-btn-${j.id}`} onClick={() => onDelete(j.id)} className="p-1.5 rounded text-[var(--pc-muted)] hover:text-red-400 opacity-60 group-hover:opacity-100"><Trash2 className="h-4 w-4" /></button>
  </li>
);

export const QueuePanel = ({ jobs, counts, activeId, onSelect, onDelete, onRetry }) => {
  const [filter, setFilter] = useState("all");
  const shown = jobs.filter((j) => matches(j, filter));
  return (
    <aside data-testid={PC.historySection} className="pc-card p-5 pc-rise lg:sticky lg:top-24">
      <div className="pc-overline mb-3">Queue & history</div>
      <div data-testid={PC.queueCounts} className="grid grid-cols-4 gap-1 mb-4 font-mono text-center">
        {[["queued", "Queued"], ["processing", "Running"], ["done", "Done"], ["error", "Failed"]].map(([k, l]) => (
          <div key={k} className="rounded bg-[var(--pc-surface2)] py-1.5">
            <div className={`text-sm ${statusColor[k]}`}>{counts[k] || 0}</div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--pc-muted)]">{l}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-1 mb-3">
        {FILTERS.map(([k, l]) => (
          <button key={k} data-testid={`queue-filter-${k}`} onClick={() => setFilter(k)}
            className={`px-2 py-1 rounded text-xs font-mono transition-colors ${filter === k ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-text2)] hover:bg-[var(--pc-surface2)]"}`}>{l}</button>
        ))}
      </div>
      {shown.length === 0 && <p data-testid={PC.historyEmpty} className="text-sm text-[var(--pc-muted)]">Nothing here yet.</p>}
      <ul className="space-y-1 max-h-[60vh] overflow-auto -mx-2">
        {shown.map((j) => <QueueItem key={j.id} j={j} active={activeId === j.id} onSelect={onSelect} onDelete={onDelete} onRetry={onRetry} />)}
      </ul>
    </aside>
  );
};
