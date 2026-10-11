import { useState } from "react";
import { Download, Plus, Flag } from "lucide-react";
import { QuestionCard } from "./QuestionCard";
import { QuestionDialog } from "./QuestionDialog";
import { MetaEditor } from "./MetaEditor";
import { DocumentsPanel } from "./DocumentsPanel";
import { DriveSetPanel } from "./DriveSet";
import { SET_STATUS } from "./QueuePanel";
import { setZipUrl, DOC_LABEL, approveAllErases } from "@/lib/api";
import { toast } from "sonner";
import { PC } from "@/constants/testIds";

const MetaChips = ({ meta }) => {
  const chips = [meta.subject, meta.grade && `Grade ${meta.grade}`, meta.year, meta.session, meta.province, meta.paper && `Paper ${meta.paper}`, meta.language].filter(Boolean);
  return chips.map((c) => <span key={c} className="px-2 py-0.5 rounded bg-[var(--pc-surface2)] font-mono text-[11px] text-[var(--pc-text2)]">{c}</span>);
};

const CatalogueLine = ({ cat }) => {
  if (!cat) return null;
  return (
    <p data-testid="set-catalogue-location" className={`mt-3 text-xs font-mono ${cat.found ? "text-[var(--pc-emerald)]" : "text-[var(--pc-amber)]"}`}>
      {cat.found ? `Catalogue: ${cat.workbook.replace(".xlsx", "")} › ${cat.sheet} › ${cat.block?.split(" - ")[1] || ""} › ${cat.row_label}` : `Catalogue: ${cat.reason}`}
    </p>
  );
};

const SetHeader = ({ set, onReset, onSetChange, docHandlers }) => {
  const [label, color] = SET_STATUS[set.status] || [set.status, ""];
  return (
    <div className="pc-card p-6 sm:p-8 space-y-5 pc-rise">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
        <div className="min-w-0">
          <div data-testid="set-status" className={`pc-overline mb-2 !${color}`}>{label}</div>
          <p className="font-heading text-2xl font-extrabold break-all">{set.base_name || "New paper set"}</p>
          <div data-testid={PC.metaBar} className="flex flex-wrap items-center gap-2 mt-3">
            <MetaChips meta={set.meta} />
            <MetaEditor set={set} onSetChange={onSetChange} />
          </div>
          <CatalogueLine cat={set.catalogue} />
          <div className="mt-3"><DriveSetPanel set={set} onSetChange={onSetChange} /></div>
        </div>
        <div className="flex gap-3 flex-wrap shrink-0">
          <button data-testid={PC.newPdfButton} onClick={onReset} className="pc-btn-secondary"><Plus className="h-4 w-4" /> Upload more</button>
          {set.erase_pending > 0 && (
            <button data-testid="approve-all-erases-button" className="pc-btn-secondary !border-red-400/60"
              onClick={async () => {
                if (!window.confirm(`Approve every AI-suggested erase in this set (${set.erase_pending} images)? Check a few first in each image's Erase tab.`)) return;
                try { onSetChange(await approveAllErases(set.id)); toast.success("Erases applied"); } catch { toast.error("Could not apply erases"); }
              }}>
              Approve all erases ({set.erase_pending})
            </button>
          )}
          {set.qp_id && <a data-testid={PC.downloadZip} href={setZipUrl(set.id)} className="pc-btn-primary"><Download className="h-4 w-4" /> Download ZIP</a>}
        </div>
      </div>
      <DocumentsPanel set={set} {...docHandlers} />
    </div>
  );
};

export const SetView = ({ set, onReset, onSetChange, docHandlers }) => {
  const [open, setOpen] = useState(null);
  const [tab, setTab] = useState("question_paper");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const docs = set.documents.filter((d) => d.meta.doc_type === tab && d.status === "done");
  const tabs = ["question_paper", "memo", "addendum", "errata"].filter((t) => set.documents.some((d) => d.meta.doc_type === t && d.status === "done"));
  const isQp = tab === "question_paper";
  const openDoc = open && set.documents.find((d) => d.id === open.jobId);

  return (
    <section data-testid={PC.resultsSection} className="space-y-6">
      <SetHeader set={set} onReset={onReset} onSetChange={onSetChange} docHandlers={docHandlers} />
      {tabs.length > 0 && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex gap-1 p-1 rounded-lg bg-[var(--pc-surface)] border border-[var(--pc-border)]">
            {tabs.map((t) => (
              <button key={t} data-testid={`set-tab-${t}`} onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${tab === t ? "bg-[var(--pc-surface2)] text-[var(--pc-text)]" : "text-[var(--pc-text2)] hover:text-[var(--pc-text)]"}`}>{DOC_LABEL[t]}</button>
            ))}
          </div>
          <p className="text-sm text-[var(--pc-text2)] flex items-center gap-3">
            <span><span data-testid={PC.questionCount} className="font-mono text-[var(--pc-amber)]">{docs.reduce((n, d) => n + d.questions.length, 0)}</span> images</span>
            {isQp && set.flagged > 0 && (
              <button data-testid="filter-flagged-button" onClick={() => setOnlyFlagged(!onlyFlagged)}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded font-mono text-xs ${onlyFlagged ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-amber)] border border-[var(--pc-amber)]/50"}`}>
                <Flag className="h-3 w-3" /> {set.flagged} need review
              </button>
            )}
          </p>
        </div>
      )}
      {docs.map((d) => (
        <div key={d.id} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-start">
          {d.questions.filter((q) => !onlyFlagged || !isQp || set.links[q.id]?.flags?.length).map((q, i) => (
            <QuestionCard key={q.id} jobId={d.id} q={q} index={i} link={isQp ? set.links[q.id] : null} onOpen={(qid) => setOpen({ jobId: d.id, qid })} />
          ))}
        </div>
      ))}
      <QuestionDialog topics={set.catalogue?.topics || []} doc={openDoc} qid={open?.qid} documents={set.documents} link={openDoc?.meta.doc_type === "question_paper" ? set.links[open?.qid] : null}
        onClose={() => setOpen(null)} onSetChange={onSetChange} />
    </section>
  );
};
