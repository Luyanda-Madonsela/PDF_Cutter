import { Scissors } from "lucide-react";
import { PC } from "@/constants/testIds";
import { UserMenu } from "./UserMenu";
import { AiBadge } from "./AiSettings";

const MODES = [["single", "One paper"], ["bulk", "Bulk upload"]];

export const Header = ({ mode, onMode }) => (
  <header data-testid={PC.header} className="sticky top-0 z-30 border-b border-[var(--pc-border)] bg-[var(--pc-bg)]/80 backdrop-blur-md">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-9 w-9 rounded-md bg-[var(--pc-amber)] text-[#0B0F19] grid place-items-center shrink-0">
          <Scissors className="h-5 w-5" strokeWidth={2.5} />
        </div>
        <div className="leading-tight hidden sm:block">
          <div className="font-heading font-extrabold text-lg tracking-tight">PaperCut</div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--pc-muted)]">Past paper question splitter</div>
        </div>
      </div>
      <nav data-testid={PC.modeSwitch} className="flex p-1 rounded-lg bg-[var(--pc-surface2)] border border-[var(--pc-border)]">
        {MODES.map(([k, l]) => (
          <button key={k} data-testid={`mode-${k}-button`} onClick={() => onMode(k)}
            className={`px-3 sm:px-4 py-1.5 rounded-md text-sm font-medium transition-colors duration-150 ${mode === k ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-text2)] hover:text-[var(--pc-text)]"}`}>
            {l}
          </button>
        ))}
      </nav>
      <AiBadge />
      <UserMenu />
    </div>
  </header>
);
