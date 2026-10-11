import { DIFFICULTY } from "@/lib/api";

export const DifficultyPicker = ({ value, onPick, testId }) => (
  <div data-testid={testId} className="flex items-center gap-2 flex-wrap mb-3">
    <span className="text-xs font-mono text-[var(--pc-muted)]">Difficulty</span>
    {Object.entries(DIFFICULTY).map(([k, [name, tone]]) => (
      <button key={k} data-testid={`${testId}-${k.toLowerCase()}`} onClick={() => k !== value && onPick(k)}
        className={`px-2.5 py-1 rounded border text-xs font-mono transition-colors ${k === value ? `${tone} bg-white/10` : "border-[var(--pc-border)] text-[var(--pc-text2)] hover:text-[var(--pc-text)]"}`}>
        {name}
      </button>
    ))}
  </div>
);
