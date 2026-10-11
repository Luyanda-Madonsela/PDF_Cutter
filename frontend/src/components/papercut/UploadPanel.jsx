import { useRef, useState } from "react";
import { FileUp, FileText, Loader2 } from "lucide-react";
import { PC } from "@/constants/testIds";

export const UploadPanel = ({ onUpload, uploading, uploadProgress }) => {
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const pick = (f) => f && f.name.toLowerCase().endsWith(".pdf") && setFile(f);

  return (
    <div className="pc-card p-6 sm:p-8 pc-rise">
      <div className="pc-overline mb-3">01 — Feed a paper</div>
      <div
        data-testid={PC.dropzone}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}
        className={`pc-dropzone cursor-pointer rounded-lg border-2 border-dashed px-6 py-14 flex flex-col items-center text-center transition-colors duration-200 ${drag ? "border-[var(--pc-amber)] bg-[var(--pc-amber)]/5" : "border-[var(--pc-border)] hover:border-[var(--pc-text2)]"}`}
      >
        <input ref={inputRef} data-testid={PC.fileInput} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
        <FileUp className="h-10 w-10 text-[var(--pc-amber)] mb-4" strokeWidth={1.5} />
        <p className="font-heading text-xl font-bold">Drop a past paper PDF here</p>
        <p className="text-sm text-[var(--pc-text2)] mt-1">or click to browse — one PDF at a time</p>
        {file && (
          <div data-testid={PC.selectedFile} className="mt-6 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--pc-surface2)] font-mono text-xs">
            <FileText className="h-4 w-4" /> {file.name} · {(file.size / 1048576).toFixed(1)} MB
          </div>
        )}
      </div>
      <button
        data-testid={PC.uploadButton}
        disabled={!file || uploading}
        onClick={() => onUpload(file)}
        className="pc-btn-primary mt-6 w-full sm:w-auto"
      >
        {uploading ? <><Loader2 className="h-4 w-4 animate-spin" /> Uploading {Math.round(uploadProgress * 100)}%</> : "Split into questions"}
      </button>
    </div>
  );
};
