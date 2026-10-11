import { useState } from "react";
import { Download, Plus } from "lucide-react";
import { QuestionCard } from "./QuestionCard";
import { QuestionDialog } from "./QuestionDialog";
import { MetaEditor } from "./MetaEditor";
import { PairBar } from "./PairBar";
import { zipUrl } from "@/lib/api";
import { PC } from "@/constants/testIds";

const MetaChips = ({ meta }) => {
  const chips = [meta.subject, meta.grade && `Grade ${meta.grade}`, meta.year, meta.session, meta.province, meta.paper && `Paper ${meta.paper}`, meta.doc_type === "memo" && "Memo"].filter(Boolean);
  return chips.map((c) => <span key={c} className="px-2 py-0.5 rounded bg-[var(--pc-surface2)] font-mono text-[11px] text-[var(--pc-text2)]">{c}</span>);
};

export const ResultsPanel = ({ job, onReset, onJobChange, onAttachMemo, onOpenJob }) => {
  const [openId, setOpenId] = useState(null);

  return (
    <section data-testid={PC.resultsSection} className="space-y-6">
      <div className="pc-card p-6 sm:p-8 space-y-5 pc-rise">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="pc-overline mb-2">03 — Done</div>
            <p className="font-heading text-2xl font-extrabold break-all">{job.base_name || job.filename}</p>
            <p className="text-xs font-mono text-[var(--pc-muted)] mt-1 truncate">{job.filename}</p>
            <div data-testid={PC.metaBar} className="flex flex-wrap items-center gap-2 mt-3">
              <MetaChips meta={job.meta} />
              <MetaEditor job={job} onJobChange={onJobChange} />
            </div>
          </div>
          <div className="flex gap-3 flex-wrap shrink-0">
            <button data-testid={PC.newPdfButton} onClick={onReset} className="pc-btn-secondary"><Plus className="h-4 w-4" /> Upload more</button>
            <a data-testid={PC.downloadZip} href={zipUrl(job.id)} className="pc-btn-primary"><Download className="h-4 w-4" /> Download ZIP</a>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--pc-border)]">
          <p className="text-sm text-[var(--pc-text2)]">
            <span data-testid={PC.questionCount} className="font-mono text-[var(--pc-amber)]">{job.questions.length}</span> images from {job.total_pages} pages · click one to view, adjust or merge
          </p>
          <PairBar job={job} onAttach={onAttachMemo} onOpen={onOpenJob} />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {job.questions.map((q, i) => (
          <QuestionCard key={q.id} jobId={job.id} q={q} index={i} onOpen={setOpenId} hasPartner={!!job.pair_map?.[q.id]} />
        ))}
      </div>

      <QuestionDialog job={job} qid={openId} onClose={() => setOpenId(null)} onJobChange={onJobChange} />
    </section>
  );
};
