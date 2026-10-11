import { useEffect, useState } from "react";
import { Download, Merge, Trash2, Flag, Check } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CropEditor } from "./CropEditor";
import { EraseReview } from "./EraseReview";
import { LinkedList } from "./LinkedEditor";
import { imageUrl, updateQuestion, mergeNext, deleteQuestion, reviewQuestion, decideErase, undoCrop } from "@/lib/api";
import { PC } from "@/constants/testIds";

const ImgBox = ({ src, alt }) => (
  <div className="max-h-[60vh] overflow-auto rounded-md bg-white"><img src={src} alt={alt} className="w-full" /></div>
);

const FlagBox = ({ flags, onReview }) => (
  <div data-testid="question-flags" className="rounded-md border border-[var(--pc-amber)]/50 bg-[var(--pc-amber)]/10 p-3 flex items-start gap-3">
    <Flag className="h-4 w-4 text-[var(--pc-amber)] mt-0.5 shrink-0" />
    <ul className="text-sm flex-1 space-y-0.5">{flags.map((f) => <li key={f}>{f}</li>)}</ul>
    <button data-testid="mark-reviewed-button" onClick={onReview} className="pc-btn-secondary !py-1.5 text-xs"><Check className="h-3.5 w-3.5" /> Mark reviewed</button>
  </div>
);

export const QuestionDialog = ({ doc, link, qid, onClose, onSetChange, topics, documents = [] }) => {
  const idx = doc ? doc.questions.findIndex((q) => q.id === qid) : -1;
  const q = idx >= 0 ? doc.questions[idx] : null;
  const [label, setLabel] = useState("");
  const [marks, setMarks] = useState("");
  const [topic, setTopic] = useState("");
  const [tab, setTab] = useState("question");
  useEffect(() => { setLabel(q?.label || ""); setMarks(q?.marks ?? ""); setTopic(q?.topic || ""); }, [q?.label, q?.marks, q?.topic]);
  const isQp = doc?.meta.doc_type === "question_paper";
  useEffect(() => { setTab("question"); }, [qid]);
  const dirty = q && (label.trim() !== q.label || String(marks) !== String(q.marks ?? "") || topic !== (q.topic || ""));
  const flags = link ? link.flags : q && !q.reviewed ? q.flags : [];

  const act = async (fn, msg, close) => {
    try { onSetChange(await fn()); toast.success(msg); if (close) onClose(); }
    catch (e) { toast.error(e.response?.data?.detail || "Action failed"); }
  };
  const v = q ? `?v=${q.storage_path.slice(-12)}` : "";

  return (
    <Dialog open={!!q} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid={PC.lightbox} className="max-w-4xl max-h-[92vh] overflow-auto bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)]">
        {q && (
          <>
            <div className="flex items-center justify-between gap-3 pr-8 flex-wrap">
              <div>
                <DialogTitle className="font-heading text-xl">Q{q.label}</DialogTitle>
                <DialogDescription className="text-xs font-mono text-[var(--pc-muted)]">Pages {q.pages.join(", ")}{q.marks != null ? ` · ${q.marks} marks` : ""}</DialogDescription>
              </div>
              <a data-testid={PC.lightboxDownload} href={imageUrl(doc.id, q.id) + v} download={q.filename} className="pc-btn-secondary text-xs font-mono break-all"><Download className="h-4 w-4 shrink-0" /> {q.filename}</a>
            </div>
            {flags.length > 0 && <FlagBox flags={flags} onReview={() => act(() => reviewQuestion(doc.id, q.id), "Marked as reviewed")} />}
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="bg-[var(--pc-surface2)] flex-wrap h-auto">
                <TabsTrigger data-testid={PC.tabQuestion} value="question">Image</TabsTrigger>
                {link?.memo && <TabsTrigger data-testid={PC.tabPartner} value="memo">Memo</TabsTrigger>}
                {link?.addenda?.length > 0 && <TabsTrigger data-testid="lightbox-tab-addendum" value="addendum">Addendum ({link.addenda.length})</TabsTrigger>}
                {link?.errata?.length > 0 && <TabsTrigger data-testid="lightbox-tab-errata" value="errata">Errata ({link.errata.length})</TabsTrigger>}
                <TabsTrigger data-testid="lightbox-tab-erase" value="erase">Erase{q.erase_status === "pending" ? " (needs approval)" : ""}</TabsTrigger>
                <TabsTrigger data-testid={PC.tabAdjust} value="adjust">Adjust crop</TabsTrigger>
              </TabsList>
              <TabsContent value="question"><ImgBox src={imageUrl(doc.id, q.id) + v} alt={q.label} /></TabsContent>
              {link?.memo && <TabsContent value="memo"><LinkedList refs={[link.memo]} kind="memo" documents={documents} onSetChange={onSetChange} /></TabsContent>}
              {link?.addenda?.length > 0 && <TabsContent value="addendum"><LinkedList refs={link.addenda} kind="addendum" documents={documents} onSetChange={onSetChange} /></TabsContent>}
              {link?.errata?.length > 0 && <TabsContent value="errata"><LinkedList refs={link.errata} kind="errata" documents={documents} onSetChange={onSetChange} /></TabsContent>}
              <TabsContent value="erase">
                <EraseReview doc={doc} q={q} onDecide={(boxes, manual) => act(() => decideErase(doc.id, q.id, boxes, manual), boxes.length + manual.length ? "Erase applied" : "Original kept").then(() => setTab("question"))} />
              </TabsContent>
              <TabsContent value="adjust">
                <CropEditor key={q.storage_path} jobId={doc.id} question={q} totalPages={doc.total_pages}
                  onSave={(parts) => act(() => updateQuestion(doc.id, q.id, { parts }), "Crop updated").then(() => setTab("question"))}
                  onUndoSaved={() => act(() => undoCrop(doc.id, q.id), "Previous crop restored")} />
              </TabsContent>
            </Tabs>
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[var(--pc-border)]">
              <input data-testid={PC.labelInput} value={label} onChange={(e) => setLabel(e.target.value)}
                className="w-24 px-3 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] font-mono text-sm focus:outline-none focus:border-[var(--pc-amber)]" />
              <input data-testid="question-marks-input" type="number" min="0" value={marks} placeholder="marks" onChange={(e) => setMarks(e.target.value)}
                className="w-24 px-3 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] font-mono text-sm focus:outline-none focus:border-[var(--pc-amber)]" />
              {isQp && topics.length > 0 && (
                <select data-testid="question-topic-select" value={topic} onChange={(e) => setTopic(e.target.value)}
                  className="max-w-[14rem] px-2 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] text-sm focus:outline-none focus:border-[var(--pc-amber)]">
                  <option value="">No topic</option>
                  {topics.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
              <button data-testid={PC.labelSave} disabled={!label.trim() || !dirty}
                onClick={() => act(() => updateQuestion(doc.id, q.id, { label, topic, ...(marks === "" ? { clear_marks: true } : { marks: Number(marks) }) }), "Question updated")}
                className="pc-btn-secondary text-sm disabled:opacity-40">Save</button>
              <div className="flex-1" />
              {idx < doc.questions.length - 1 && (
                <button data-testid={PC.mergeNext} onClick={() => act(() => mergeNext(doc.id, q.id), `Merged Q${doc.questions[idx + 1].label} into Q${q.label}`)} className="pc-btn-secondary text-sm">
                  <Merge className="h-4 w-4" /> Merge with Q{doc.questions[idx + 1].label}
                </button>
              )}
              <button data-testid={PC.deleteQuestion} onClick={() => act(() => deleteQuestion(doc.id, q.id), "Image removed", true)} className="pc-btn-secondary text-sm hover:!text-red-400">
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
