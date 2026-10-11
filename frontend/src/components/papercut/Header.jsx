import { Scissors } from "lucide-react";
import { PC } from "@/constants/testIds";

export const Header = () => (
  <header data-testid={PC.header} className="sticky top-0 z-30 border-b border-[var(--pc-border)] bg-[var(--pc-bg)]/80 backdrop-blur-md">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-md bg-[var(--pc-amber)] text-[#0B0F19] grid place-items-center">
          <Scissors className="h-5 w-5" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="font-heading font-extrabold text-lg tracking-tight">PaperCut</div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--pc-muted)]">Past paper question splitter</div>
        </div>
      </div>
      <div data-testid={PC.modelBadge} className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full border border-[var(--pc-border)] font-mono text-xs text-[var(--pc-text2)]">
        <span className="h-2 w-2 rounded-full bg-[var(--pc-emerald)] animate-pulse" />
        gemini-3-flash
      </div>
    </div>
  </header>
);
