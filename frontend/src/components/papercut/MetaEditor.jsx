import { useState } from "react";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { updateMeta } from "@/lib/api";
import { PC } from "@/constants/testIds";

const FIELDS = [["subject", "Subject"], ["grade", "Grade"], ["year", "Year"], ["session", "Session"], ["paper", "Paper no."], ["language", "Language"]];

export const MetaEditor = ({ job, onJobChange }) => {
  const [open, setOpen] = useState(false);
  const [meta, setMeta] = useState(job.meta);

  const save = async () => {
    try { onJobChange(await updateMeta(job.id, meta)); toast.success("Details updated — files renamed"); setOpen(false); }
    catch (e) { toast.error(e.response?.data?.detail || "Update failed"); }
  };

  return (
    <>
      <button data-testid={PC.editMetaButton} onClick={() => { setMeta(job.meta); setOpen(true); }} className="inline-flex items-center gap-1 text-xs font-mono text-[var(--pc-text2)] hover:text-[var(--pc-amber)]">
        <Pencil className="h-3 w-3" /> edit details
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={PC.metaDialog} className="max-w-md bg-[var(--pc-surface)] border-[var(--pc-border)] text-[var(--pc-text)]">
          <DialogTitle className="font-heading text-xl">Paper details</DialogTitle>
          <DialogDescription className="text-xs text-[var(--pc-text2)]">Used for file names and memo matching.</DialogDescription>
          <div className="grid grid-cols-2 gap-3">
            {FIELDS.map(([k, l]) => (
              <label key={k} className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-[var(--pc-muted)]">{l}</span>
                <input data-testid={`meta-input-${k}`} value={meta[k] || ""} onChange={(e) => setMeta({ ...meta, [k]: e.target.value })}
                  className="w-full px-3 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] text-sm focus:outline-none focus:border-[var(--pc-amber)]" />
              </label>
            ))}
            <label className="space-y-1 col-span-2">
              <span className="text-[11px] font-mono uppercase tracking-wider text-[var(--pc-muted)]">Document type</span>
              <select data-testid="meta-input-doc-type" value={meta.doc_type} onChange={(e) => setMeta({ ...meta, doc_type: e.target.value })}
                className="w-full px-3 py-2 rounded-md bg-[var(--pc-surface2)] border border-[var(--pc-border)] text-sm">
                <option value="question_paper">Question paper</option>
                <option value="memo">Memo / marking guideline</option>
              </select>
            </label>
          </div>
          <button data-testid={PC.metaSave} onClick={save} className="pc-btn-primary mt-2">Save & rename files</button>
        </DialogContent>
      </Dialog>
    </>
  );
};
