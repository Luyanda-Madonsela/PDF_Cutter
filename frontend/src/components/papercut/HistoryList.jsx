import { Download, Trash2 } from "lucide-react";
import { zipUrl } from "@/lib/api";
import { PC } from "@/constants/testIds";

const statusColor = { done: "text-[var(--pc-emerald)]", error: "text-red-400", processing: "text-[var(--pc-amber)]", queued: "text-[var(--pc-amber)]" };

export const HistoryList = ({ jobs, activeId, onSelect, onDelete }) => (
  <aside data-testid={PC.historySection} className="pc-card p-5 pc-rise">
    <div className="pc-overline mb-4">History</div>
    {jobs.length === 0 && <p data-testid={PC.historyEmpty} className="text-sm text-[var(--pc-muted)]">No papers processed yet.</p>}
    <ul className="space-y-1 max-h-[70vh] overflow-auto -mx-2">
      {jobs.map((j) => (
        <li key={j.id} className={`group flex items-center gap-2 px-2 py-2 rounded-md transition-colors duration-150 ${activeId === j.id ? "bg-[var(--pc-surface2)]" : "hover:bg-[var(--pc-surface2)]/60"}`}>
          <button data-testid={`history-item-${j.id}`} onClick={() => onSelect(j.id)} className="flex-1 min-w-0 text-left">
            <p className="text-sm truncate">{j.filename}</p>
            <p className={`font-mono text-[11px] ${statusColor[j.status]}`}>{j.status} · {j.total_pages || "?"}p · {new Date(j.created_at).toLocaleDateString()}</p>
          </button>
          {j.status === "done" && (
            <a data-testid={`history-redownload-btn-${j.id}`} href={zipUrl(j.id)} className="p-1.5 rounded text-[var(--pc-text2)] hover:text-[var(--pc-amber)]"><Download className="h-4 w-4" /></a>
          )}
          <button data-testid={`history-delete-btn-${j.id}`} onClick={() => onDelete(j.id)} className="p-1.5 rounded text-[var(--pc-muted)] hover:text-red-400 opacity-60 group-hover:opacity-100"><Trash2 className="h-4 w-4" /></button>
        </li>
      ))}
    </ul>
  </aside>
);
