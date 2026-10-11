import { Layers, BookCheck } from "lucide-react";
import { imageUrl } from "@/lib/api";

export const QuestionCard = ({ jobId, q, onOpen, index, hasPartner }) => (
  <button
    data-testid={`question-card-${q.order}`}
    onClick={() => onOpen(q.id)}
    style={{ animationDelay: `${Math.min(index, 20) * 30}ms` }}
    className="pc-card pc-rise group text-left overflow-hidden hover:border-[var(--pc-amber)] transition-colors duration-200"
  >
    <div className="h-44 bg-white overflow-hidden">
      <img data-testid={`question-image-${q.order}`} src={imageUrl(jobId, q.id) + `?v=${q.storage_path.slice(-12)}`} alt={`Question ${q.label}`} loading="lazy"
        className="w-full object-cover object-top group-hover:scale-[1.02] transition-transform duration-300" />
    </div>
    <div className="p-3 flex items-center justify-between gap-2 border-t border-[var(--pc-border)]">
      <span className="flex items-center gap-1.5 min-w-0">
        <span data-testid={`question-label-${q.order}`} className="pc-badge">Q {q.label}</span>
        {q.marks != null && <span data-testid={`question-marks-${q.order}`} className="font-mono text-[11px] text-[var(--pc-text2)]">{q.marks}m</span>}
      </span>
      <span className="font-mono text-[11px] text-[var(--pc-muted)] flex items-center gap-1.5">
        {hasPartner && <BookCheck data-testid={`question-has-partner-${q.order}`} className="h-3.5 w-3.5 text-[var(--pc-emerald)]" />}
        {q.pages.length > 1 && <Layers className="h-3 w-3 text-[var(--pc-amber)]" />}
        p.{q.pages.join("–")}
      </span>
    </div>
  </button>
);
