import { useState } from "react";
import { Download, Plus } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { QuestionCard } from "./QuestionCard";
import { imageUrl, zipUrl } from "@/lib/api";
import { PC } from "@/constants/testIds";

export const ResultsPanel = ({ job, onReset }) => {
  const [open, setOpen] = useState(null);

  return (
    <section data-testid={PC.resultsSection} className="space-y-6">
      <div className="pc-card p-6 sm:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 pc-rise">
        <div className="min-w-0">
          <div className="pc-overline mb-2">03 — Done</div>
          <p className="font-heading text-2xl font-extrabold truncate">{job.filename}</p>
          <p className="text-sm text-[var(--pc-text2)] mt-1">
            <span data-testid={PC.questionCount} className="font-mono text-[var(--pc-amber)]">{job.questions.length}</span> question images from {job.total_pages} pages
          </p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button data-testid={PC.newPdfButton} onClick={onReset} className="pc-btn-secondary"><Plus className="h-4 w-4" /> New PDF</button>
          <a data-testid={PC.downloadZip} href={zipUrl(job.id)} className="pc-btn-primary"><Download className="h-4 w-4" /> Download ZIP</a>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {job.questions.map((q, i) => <QuestionCard key={q.filename} jobId={job.id} q={q} index={i} onOpen={setOpen} />)}
      </div>

      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent data-testid={PC.lightbox} className="max-w-4xl bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)]">
          {open && (
            <>
              <div className="flex items-center justify-between pr-8">
                <DialogTitle className="font-heading text-xl">Question {open.label}</DialogTitle>
                <a data-testid={PC.lightboxDownload} href={imageUrl(job.id, open.filename)} download={open.filename} className="pc-btn-secondary text-sm">
                  <Download className="h-4 w-4" /> {open.filename}
                </a>
              </div>
              <div className="max-h-[75vh] overflow-auto rounded-md bg-white">
                <img src={imageUrl(job.id, open.filename)} alt={open.label} className="w-full" />
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
};
