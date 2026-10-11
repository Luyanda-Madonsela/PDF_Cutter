import { Layers, BookCheck, Flag, Paperclip, FileWarning } from "lucide-react";
import { imageUrl } from "@/lib/api";

export const QuestionCard = ({ jobId, q, onOpen, index, link }) => (
  <button
    data-testid={`question-card-${q.order}`}
    onClick={() => onOpen(q.id)}
    style={{ animationDelay: `${Math.min(index, 20) * 30}ms` }}
    className={`pc-card pc-rise group text-left overflow-hidden transition-colors duration-200 ${link?.flags?.length ? "!border-[var(--pc-amber)]/70" : "hover:border-[var(--pc-amber)]"}`}
  >
    <div className="max-h-56 bg-white overflow-hidden">
      <img data-testid={`question-image-${q.order}`} src={imageUrl(jobId, q.id) + `?v=${q.storage_path.slice(-12)}`} alt={`Question ${q.label}`} loading="lazy"
        className="w-full block group-hover:scale-[1.02] transition-transform duration-300" />
    </div>
    <div className="p-3 flex items-center justify-between gap-2 border-t border-[var(--pc-border)]">
      <span className="flex items-center gap-1.5 min-w-0 whitespace-nowrap">
        <span data-testid={`question-label-${q.order}`} className="pc-badge">Q {q.label}</span>
        {q.marks != null && <span data-testid={`question-marks-${q.order}`} className="font-mono text-[11px] text-[var(--pc-text2)]">{q.marks}m</span>}
      </span>
      <span className="font-mono text-[11px] text-[var(--pc-muted)] flex items-center gap-1.5">
        {link?.flags?.length > 0 && <Flag data-testid={`question-flag-${q.order}`} className="h-3.5 w-3.5 text-[var(--pc-amber)]" />}
        {link?.memo && <BookCheck data-testid={`question-has-memo-${q.order}`} className="h-3.5 w-3.5 text-[var(--pc-emerald)]" />}
        {link?.addenda?.length > 0 && <Paperclip data-testid={`question-has-addendum-${q.order}`} className="h-3.5 w-3.5 text-sky-400" />}
        {link?.errata?.length > 0 && <FileWarning data-testid={`question-has-errata-${q.order}`} className="h-3.5 w-3.5 text-red-400" />}
        {q.pages.length > 1 && <Layers className="h-3 w-3 text-[var(--pc-amber)]" />}
        <span className="hidden xl:inline">p.{q.pages.join("–")}</span>
      </span>
    </div>
  </button>
);
