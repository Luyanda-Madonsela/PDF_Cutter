import { useState } from "react";
import { Scissors, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { recropPreview, recropAll, recropSet } from "@/lib/api";

const edited = (q) => q.reviewed || ["applied", "rejected"].includes(q.erase_status) || q.erase_manual?.length;

const Confirm = ({ open, onOpenChange, title, text, onConfirm, testid }) => (
  <AlertDialog open={open} onOpenChange={onOpenChange}>
    <AlertDialogContent data-testid={testid} className="bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)]">
      <AlertDialogHeader>
        <AlertDialogTitle className="font-heading">{title}</AlertDialogTitle>
        <AlertDialogDescription className="text-[var(--pc-text2)]">{text}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel data-testid={`${testid}-cancel`}>Cancel</AlertDialogCancel>
        <AlertDialogAction data-testid={`${testid}-confirm`} onClick={onConfirm} className="bg-[var(--pc-amber)] text-[#0B0F19] hover:bg-[var(--pc-amber)]/90">Re-crop</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

const TAIL = "Memos, addenda and errata are kept. Once it's done, the set uploads to Drive again.";

export const RecropSetButton = ({ set, onSetChange }) => {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (set.status !== "done") return null;
  const qp = set.documents.find((d) => d.id === set.qp_id);
  const n = qp ? qp.questions.filter(edited).length : 0;
  const go = async () => {
    setBusy(true);
    try { onSetChange(await recropSet(set.id)); toast.success("Re-cropping the question paper"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not re-crop"); }
    setBusy(false);
  };
  return (
    <>
      <button data-testid="recrop-set-button" disabled={busy || !qp} onClick={() => setOpen(true)} className="pc-btn-secondary !py-1 text-xs">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Scissors className="h-3.5 w-3.5" />} Re-crop
      </button>
      <Confirm open={open} onOpenChange={setOpen} testid="recrop-set-dialog" onConfirm={go} title="Re-crop this question paper?"
        text={`${n ? `${n} question${n > 1 ? "s have" : " has"} manual edits (crops, erases, renames or topics), and they will be lost. ` : "No manual edits will be lost. "}${TAIL}`} />
    </>
  );
};

export const RecropAllButton = ({ onDone }) => {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const ask = async () => { setBusy(true); try { setInfo(await recropPreview()); } catch { toast.error("Could not check sets"); } setBusy(false); };
  const go = async () => {
    try { const r = await recropAll(); toast.success(`${r.queued} sets queued for re-cropping`); onDone(); }
    catch { toast.error("Could not re-crop"); }
  };
  return (
    <>
      <button data-testid="recrop-all-button" disabled={busy} onClick={ask}
        className="w-full mb-3 inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-md border border-[var(--pc-border)] text-xs font-mono text-[var(--pc-text2)] hover:text-[var(--pc-text)] hover:bg-[var(--pc-surface2)] transition-colors">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Scissors className="h-3.5 w-3.5" />} Re-crop all finished sets
      </button>
      <Confirm open={!!info} onOpenChange={(o) => !o && setInfo(null)} testid="recrop-all-dialog" onConfirm={go}
        title={`Re-crop ${info?.sets || 0} paper sets?`}
        text={`${info?.edited ? `${info.edited} of them have manual edits, and those edits will be lost. ` : "None of them have manual edits. "}Each question paper is cut again with answer lines and boxes left out. ${TAIL}`} />
    </>
  );
};
