import { useState } from "react";
import { Download, Trash2, Flag } from "lucide-react";
import { setZipUrl } from "@/lib/api";
import { DriveBadge } from "./DriveSet";
import { RecropAllButton } from "./Recrop";
import { PC } from "@/constants/testIds";

export const SET_STATUS = {
  needs_memo: ["Needs memo", "text-red-400"],
  needs_paper: ["Needs paper", "text-red-400"],
  processing: ["Processing", "text-[var(--pc-amber)]"],
  done: ["Done", "text-[var(--pc-emerald)]"],
  error: ["Failed", "text-red-400"],
  paused: ["Paused: spending limit", "text-[var(--pc-amber)]"],
  stopped: ["Stopped", "text-red-400"],
};
const FILTERS = [["all", "All"], ["incomplete", "Incomplete"], ["flagged", "Review"], ["done", "Done"], ["error", "Failed"]];
const TILES = [["sorting", "Sorting"], ["needs_memo", "No memo"], ["processing", "Running"], ["done", "Done"], ["flagged", "Review"]];
const DOC_CHIP = { question_paper: "QP", memo: "M", addendum: "A", errata: "E" };

const matches = (s, f) => f === "all" || (f === "incomplete" ? s.status.startsWith("needs") : f === "flagged" ? s.flagged > 0 : s.status === f);

const SetItem = ({ s, active, onSelect, onDelete }) => {
  const [label, color] = SET_STATUS[s.status] || [s.status, ""];
  const chips = Object.entries(s.docs.reduce((a, d) => ({ ...a, [d.doc_type]: (a[d.doc_type] || 0) + 1 }), {}));
  return (
    <li className={`group flex items-center gap-2 px-2 py-2 rounded-md transition-colors duration-150 ${active ? "bg-[var(--pc-surface2)]" : "hover:bg-[var(--pc-surface2)]/60"}`}>
      <button data-testid={`set-item-${s.id}`} onClick={() => onSelect(s.id)} className="flex-1 min-w-0 text-left">
        <p className="text-sm truncate">{s.base_name || s.docs[0]?.filename || "Untitled set"}</p>
        <p className="font-mono text-[11px] flex items-center gap-1.5 flex-wrap">
          <span className={color}>{label}</span>
          {chips.map(([t, n]) => <span key={t} className="text-[var(--pc-muted)]">{DOC_CHIP[t]}{n > 1 ? `×${n}` : ""}</span>)}
          {s.flagged > 0 && <span className="text-[var(--pc-amber)] flex items-center gap-0.5"><Flag className="h-3 w-3" />{s.flagged}</span>}
          <DriveBadge drive={s.drive} compact />
        </p>
      </button>
      {s.status === "done" && <a data-testid={`set-download-${s.id}`} href={setZipUrl(s.id)} className="p-1.5 rounded text-[var(--pc-text2)] hover:text-[var(--pc-amber)]"><Download className="h-4 w-4" /></a>}
      <button data-testid={`set-delete-${s.id}`} onClick={() => onDelete(s.id)} className="p-1.5 rounded text-[var(--pc-muted)] hover:text-red-400 opacity-60 group-hover:opacity-100"><Trash2 className="h-4 w-4" /></button>
    </li>
  );
};

export const QueuePanel = ({ sets, counts, activeId, onSelect, onDelete, onRefresh }) => {
  const [filter, setFilter] = useState("all");
  const shown = sets.filter((s) => matches(s, filter));
  return (
    <aside data-testid={PC.historySection} className="pc-card p-5 pc-rise">
      <div className="pc-overline mb-3">Paper sets</div>
      {(counts.done || 0) > 0 && <RecropAllButton onDone={onRefresh} />}
      <div data-testid={PC.queueCounts} className="grid grid-cols-5 gap-1 mb-4 font-mono text-center">
        {TILES.map(([k, l]) => (
          <div key={k} className="rounded bg-[var(--pc-surface2)] py-1.5">
            <div className="text-sm">{k === "needs_memo" ? (counts.needs_memo || 0) + (counts.needs_paper || 0) : counts[k] || 0}</div>
            <div className="text-[8px] uppercase tracking-wider text-[var(--pc-muted)]">{l}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-1 mb-3 flex-wrap">
        {FILTERS.map(([k, l]) => (
          <button key={k} data-testid={`queue-filter-${k}`} onClick={() => setFilter(k)}
            className={`px-2 py-1 rounded text-xs font-mono transition-colors ${filter === k ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-text2)] hover:bg-[var(--pc-surface2)]"}`}>{l}</button>
        ))}
      </div>
      {shown.length === 0 && <p data-testid={PC.historyEmpty} className="text-sm text-[var(--pc-muted)]">Nothing here yet.</p>}
      <ul className="space-y-1 max-h-[60vh] overflow-auto -mx-2">
        {shown.map((s) => <SetItem key={s.id} s={s} active={activeId === s.id} onSelect={onSelect} onDelete={onDelete} />)}
      </ul>
    </aside>
  );
};
