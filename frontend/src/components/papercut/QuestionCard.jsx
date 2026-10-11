import { Layers, BookCheck, Flag, Paperclip, FileWarning, Eraser } from "lucide-react";
import { imageUrl, DIFFICULTY } from "@/lib/api";

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
    {q.topic && <div data-testid={`question-topic-${q.order}`} className="px-3 pt-2 text-[11px] font-mono text-sky-300 truncate border-t border-[var(--pc-border)]">{q.topic}</div>}
    <div className={`p-3 flex items-center justify-between gap-2 ${q.topic ? "" : "border-t border-[var(--pc-border)]"}`}>
      <span className="flex items-center gap-1.5 min-w-0 whitespace-nowrap">
        <span data-testid={`question-label-${q.order}`} className="pc-badge">Q {q.label}</span>
        {q.marks != null && <span data-testid={`question-marks-${q.order}`} className="font-mono text-[11px] text-[var(--pc-text2)]">{q.marks}m</span>}
        {DIFFICULTY[q.difficulty] && <span data-testid={`question-difficulty-${q.order}`} className={`px-1.5 py-0.5 rounded border font-mono text-[10px] ${DIFFICULTY[q.difficulty][1]}`}>{DIFFICULTY[q.difficulty][0]}</span>}
      </span>
      <span className="font-mono text-[11px] text-[var(--pc-muted)] flex items-center gap-1.5">
        {link?.flags?.length > 0 && <Flag data-testid={`question-flag-${q.order}`} className="h-3.5 w-3.5 text-[var(--pc-amber)]" />}
        {q.erase_status === "pending" && <Eraser data-testid={`question-erase-pending-${q.order}`} className="h-3.5 w-3.5 text-red-400" />}
        {link?.memo && <BookCheck data-testid={`question-has-memo-${q.order}`} className="h-3.5 w-3.5 text-[var(--pc-emerald)]" />}
        {link?.addenda?.length > 0 && <Paperclip data-testid={`question-has-addendum-${q.order}`} className="h-3.5 w-3.5 text-sky-400" />}
        {link?.errata?.length > 0 && <FileWarning data-testid={`question-has-errata-${q.order}`} className="h-3.5 w-3.5 text-red-400" />}
        {q.pages.length > 1 && <Layers className="h-3 w-3 text-[var(--pc-amber)]" />}
        <span className="hidden xl:inline">p.{q.pages.join("–")}</span>
      </span>
    </div>
  </button>
);
