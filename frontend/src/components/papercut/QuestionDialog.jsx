import { useEffect, useState } from "react";
import { Download, Merge, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CropEditor } from "./CropEditor";
import { imageUrl, updateQuestion, mergeNext, deleteQuestion } from "@/lib/api";
import { PC } from "@/constants/testIds";

const ImgBox = ({ src, alt }) => (
  <div className="max-h-[65vh] overflow-auto rounded-md bg-white"><img src={src} alt={alt} className="w-full" /></div>
);

export const QuestionDialog = ({ job, qid, onClose, onJobChange }) => {
  const idx = job.questions.findIndex((q) => q.id === qid);
  const q = job.questions[idx];
  const [label, setLabel] = useState(q?.label || "");
  const [tab, setTab] = useState("question");
  useEffect(() => { setLabel(q?.label || ""); }, [q?.label]);

  const partnerQid = q && job.pair_map?.[q.id];
  const partner = job.paired;
  const partnerName = partner?.doc_type === "memo" ? "Memo" : "Question";
  const v = q ? `?v=${q.storage_path.slice(-12)}` : "";

  const act = async (fn, msg, close) => {
    try { const j = await fn(); onJobChange(j); toast.success(msg); if (close) onClose(); }
    catch (e) { toast.error(e.response?.data?.detail || "Action failed"); }
  };

  return (
    <Dialog open={!!q} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid={PC.lightbox} className="max-w-4xl max-h-[92vh] overflow-auto bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)]">
        {q && (
          <>
            <div className="flex items-center justify-between gap-3 pr-8 flex-wrap">
              <div><DialogTitle className="font-heading text-xl">Question {q.label}</DialogTitle><DialogDescription className="text-xs font-mono text-[var(--pc-muted)]">Pages {q.pages.join(", ")}</DialogDescription></div>
              <a data-testid={PC.lightboxDownload} href={imageUrl(job.id, q.id) + v} download={q.filename} className="pc-btn-secondary text-xs font-mono">
                <Download className="h-4 w-4" /> {q.filename}
              </a>
            </div>
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="bg-[var(--pc-surface2)]">
                <TabsTrigger data-testid={PC.tabQuestion} value="question">Image</TabsTrigger>
                {partnerQid && <TabsTrigger data-testid={PC.tabPartner} value="partner">{partnerName}</TabsTrigger>}
                <TabsTrigger data-testid={PC.tabAdjust} value="adjust">Adjust crop</TabsTrigger>
              </TabsList>
              <TabsContent value="question"><ImgBox src={imageUrl(job.id, q.id) + v} alt={q.label} /></TabsContent>
              {partnerQid && <TabsContent value="partner"><ImgBox src={imageUrl(partner.job_id, partnerQid)} alt={`${partnerName} ${q.label}`} /></TabsContent>}
              <TabsContent value="adjust">
                <CropEditor key={q.storage_path} jobId={job.id} question={q} totalPages={job.total_pages}
                  onSave={(parts) => act(() => updateQuestion(job.id, q.id, { parts }), "Crop updated").then(() => setTab("question"))} />
              </TabsContent>
            </Tabs>
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[var(--pc-border)]">
              <input data-testid={PC.labelInput} value={label} onChange={(e) => setLabel(e.target.value)}
                className="w-28 px-3 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] font-mono text-sm focus:outline-none focus:border-[var(--pc-amber)]" />
              <button data-testid={PC.labelSave} disabled={!label.trim() || label === q.label} onClick={() => act(() => updateQuestion(job.id, q.id, { label }), "Label updated")} className="pc-btn-secondary text-sm disabled:opacity-40">Rename</button>
              <div className="flex-1" />
              {idx < job.questions.length - 1 && (
                <button data-testid={PC.mergeNext} onClick={() => act(() => mergeNext(job.id, q.id), `Merged Q${job.questions[idx + 1].label} into Q${q.label}`)} className="pc-btn-secondary text-sm">
                  <Merge className="h-4 w-4" /> Merge with Q{job.questions[idx + 1].label}
                </button>
              )}
              <button data-testid={PC.deleteQuestion} onClick={() => act(() => deleteQuestion(job.id, q.id), "Image removed", true)} className="pc-btn-secondary text-sm hover:!text-red-400">
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
