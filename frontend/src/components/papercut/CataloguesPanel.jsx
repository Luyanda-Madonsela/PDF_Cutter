import { useEffect, useState } from "react";
import { FileSpreadsheet, Download } from "lucide-react";
import { listCatalogues, catalogueUrl } from "@/lib/api";

export const CataloguesPanel = ({ refreshKey }) => {
  const [cats, setCats] = useState([]);
  const [grade, setGrade] = useState("12");
  const grades = [...new Set(cats.map((c) => c.grade))];
  useEffect(() => { listCatalogues().then(setCats).catch(() => {}); }, [refreshKey]);
  return (
    <aside data-testid="catalogues-panel" className="pc-card p-5 pc-rise">
      <div className="pc-overline mb-1">Catalogues</div>
      <p className="text-[11px] text-[var(--pc-muted)] mb-3">Filled in from every finished paper. Each download is up to date.</p>
      <div className="flex gap-1 mb-3 flex-wrap">
        {grades.map((g) => (
          <button key={g} data-testid={`catalogue-grade-${g}`} onClick={() => setGrade(g)}
            className={`px-2 py-1 rounded text-xs font-mono transition-colors ${grade === g ? "bg-[var(--pc-amber)] text-[#0B0F19]" : "text-[var(--pc-text2)] hover:bg-[var(--pc-surface2)]"}`}>Gr {g}</button>
        ))}
      </div>
      <ul className="space-y-1 -mx-2">
        {cats.filter((c) => c.grade === grade).map((c) => (
          <li key={c.key}>
            <a data-testid={`catalogue-download-${c.key}`} href={catalogueUrl(c.key)}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--pc-surface2)] transition-colors group">
              <FileSpreadsheet className="h-4 w-4 text-[var(--pc-emerald)] shrink-0" />
              <span className="text-sm truncate flex-1">{c.name.replace(" Catalogue", "").replace(/^Grade \d+ /, "")}</span>
              <span data-testid={`catalogue-count-${c.key}`} className="font-mono text-[11px] text-[var(--pc-muted)]">{c.papers_filled}</span>
              <Download className="h-3.5 w-3.5 text-[var(--pc-text2)] group-hover:text-[var(--pc-amber)]" />
            </a>
          </li>
        ))}
      </ul>
    </aside>
  );
};
