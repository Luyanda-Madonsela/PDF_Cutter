import { Loader2, AlertTriangle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { PC } from "@/constants/testIds";

export const ProgressPanel = ({ job }) => {
  const pct = job.total_pages ? Math.round((job.pages_done / job.total_pages) * 100) : 0;
  const isError = job.status === "error";
  const stage = job.status === "queued" ? "Rendering pages" : job.pages_done < job.total_pages ? "AI is locating question boundaries" : "Cropping & stitching images";

  return (
    <div data-testid={PC.progressCard} className="pc-card p-6 sm:p-8 pc-rise">
      <div className="pc-overline mb-3">02 — Processing</div>
      <div className="flex items-start justify-between gap-4 mb-5">
        <div className="min-w-0">
          <p className="font-heading text-lg font-bold truncate">{job.filename}</p>
          <p className="text-sm text-[var(--pc-text2)] flex items-center gap-2 mt-1">
            {isError ? <AlertTriangle className="h-4 w-4 text-red-400" /> : <Loader2 className="h-4 w-4 animate-spin text-[var(--pc-amber)]" />}
            {isError ? "Processing failed" : stage}
          </p>
        </div>
        <span data-testid={PC.pageIndicator} className="font-mono text-sm text-[var(--pc-text2)] whitespace-nowrap">
          Page {job.pages_done} / {job.total_pages || "…"}
        </span>
      </div>
      <Progress data-testid={PC.progressBar} value={pct} className="h-2 bg-[var(--pc-surface2)]" />
      {isError && <p data-testid={PC.errorMessage} className="mt-4 text-sm text-red-400 font-mono">{job.error}</p>}
    </div>
  );
};
