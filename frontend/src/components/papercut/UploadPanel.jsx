import { useRef, useState } from "react";
import { FileUp, Files, Loader2, X } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { PC } from "@/constants/testIds";

export const UploadPanel = ({ onUpload, bulk }) => {
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);
  const busy = bulk && bulk.done < bulk.total;

  const pick = (list) => setFiles(Array.from(list || []).filter((f) => f.name.toLowerCase().endsWith(".pdf")));
  const size = files.reduce((s, f) => s + f.size, 0) / 1048576;

  return (
    <div data-testid="bulk-upload-panel" className="pc-card p-6 sm:p-8 pc-rise">
      <div className="pc-overline mb-3">Bulk upload — papers, memos, addenda & errata together</div>
      <div
        data-testid={PC.dropzone}
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); !busy && pick(e.dataTransfer.files); }}
        className={`cursor-pointer rounded-lg border-2 border-dashed px-6 py-12 flex flex-col items-center text-center transition-colors duration-200 ${drag ? "border-[var(--pc-amber)] bg-[var(--pc-amber)]/5" : "border-[var(--pc-border)] hover:border-[var(--pc-text2)]"}`}
      >
        <input ref={inputRef} data-testid={PC.fileInput} type="file" multiple accept="application/pdf,.pdf" className="hidden" onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
        <FileUp className="h-10 w-10 text-[var(--pc-amber)] mb-4" strokeWidth={1.5} />
        <p className="font-heading text-xl font-bold">Drop a folder's worth of PDFs here</p>
        <p className="text-sm text-[var(--pc-text2)] mt-1 max-w-md">The AI reads each cover and groups files into sets. A paper is only split once its memo is in the same set.</p>
        {files.length > 0 && (
          <div data-testid={PC.selectedFile} className="mt-6 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--pc-surface2)] font-mono text-xs">
            <Files className="h-4 w-4" /> {files.length} PDFs · {size.toFixed(1)} MB
            {!busy && <button data-testid={PC.clearFiles} onClick={(e) => { e.stopPropagation(); setFiles([]); }} className="ml-1 hover:text-red-400"><X className="h-3.5 w-3.5" /></button>}
          </div>
        )}
      </div>
      {busy && (
        <div data-testid={PC.bulkProgress} className="mt-6 space-y-2">
          <div className="flex justify-between font-mono text-xs text-[var(--pc-text2)]">
            <span>Uploading {bulk.done} / {bulk.total}</span>
            {bulk.failed > 0 && <span className="text-red-400">{bulk.failed} failed</span>}
          </div>
          <Progress value={(bulk.done / bulk.total) * 100} className="h-1.5 bg-[var(--pc-surface2)]" />
        </div>
      )}
      <button data-testid={PC.uploadButton} disabled={!files.length || busy} onClick={() => { onUpload(files); setFiles([]); }} className="pc-btn-primary mt-6 w-full sm:w-auto">
        {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> Uploading…</> : `Queue ${files.length || ""} PDFs`}
      </button>
    </div>
  );
};
