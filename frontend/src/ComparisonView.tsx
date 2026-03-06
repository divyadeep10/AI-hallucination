import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import DiffMatchPatch from "diff-match-patch";
import type { Claim } from "./api";

const dmp = new DiffMatchPatch();

export type ComparisonViewProps = {
  generatorResponse: string;
  refinedResponse: string;
  claims: Claim[];
  formatResponseText: (text: string) => React.ReactNode;
};

function computeImprovementSummary(claims: Claim[]) {
  const total = claims.length;
  if (total === 0) {
    return {
      total: 0,
      supported: 0,
      contradicted: 0,
      unverifiable: 0,
      unsupported: 0,
      reliabilityPct: 0,
    };
  }
  let supported = 0;
  let contradicted = 0;
  let unverifiable = 0;
  let unsupported = 0; // NO_EVIDENCE or CONTRADICTED
  for (const c of claims) {
    const s = (c.verification_status ?? "").toUpperCase();
    if (s === "SUPPORTED") supported += 1;
    else if (s === "CONTRADICTED") {
      contradicted += 1;
      unsupported += 1;
    } else if (s === "NO_EVIDENCE") {
      unverifiable += 1;
      unsupported += 1;
    } else {
      unverifiable += 1;
    }
  }
  const reliabilityPct = Math.round((supported / total) * 100);
  return {
    total,
    supported,
    contradicted,
    unverifiable,
    unsupported,
    reliabilityPct,
  };
}

function renderDiff(draft: string, refined: string, formatText: (t: string) => React.ReactNode): React.ReactNode {
  const diffs = dmp.diff_main(draft.trim(), refined.trim());
  dmp.diff_cleanupSemantic(diffs);
  const parts: React.ReactNode[] = [];
  diffs.forEach(([op, text], i) => {
    if (!text) return;
    const key = `diff-${i}`;
    if (op === -1) {
      parts.push(
        <span key={key} className="bg-red-500/20 text-red-300 line-through decoration-red-400">
          {formatText(text)}
        </span>
      );
    } else if (op === 1) {
      parts.push(
        <span key={key} className="bg-emerald-500/20 text-emerald-200">
          {formatText(text)}
        </span>
      );
    } else {
      parts.push(<span key={key}>{formatText(text)}</span>);
    }
  });
  return <>{parts}</>;
}

export function ComparisonView({
  generatorResponse,
  refinedResponse,
  claims,
  formatResponseText,
}: ComparisonViewProps) {
  const [showDiff, setShowDiff] = useState(false);
  const summary = useMemo(() => computeImprovementSummary(claims), [claims]);
  const hasSummary = summary.total > 0;

  return (
    <motion.div
      className="space-y-8"
      initial="hidden"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.08 } } }}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.section
          className="rounded-2xl p-6 sm:p-8 border border-slate-600 shadow-xl overflow-hidden"
          style={{ backgroundColor: "#0d0a1a" }}
          variants={{
            hidden: { opacity: 0, x: -24 },
            visible: { opacity: 0.85, x: 0 },
          }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
          aria-labelledby="comparison-draft-heading"
        >
          <h2
            id="comparison-draft-heading"
            className="m-0 mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400"
          >
            Original Draft
          </h2>
          <div className="text-slate-300 text-base leading-relaxed font-light">
            {formatResponseText(generatorResponse)}
          </div>
        </motion.section>

        <motion.section
          className="rounded-2xl p-6 sm:p-8 border border-emerald-500/30 shadow-xl overflow-hidden ring-1 ring-emerald-500/20"
          style={{ backgroundColor: "#0d0a1a", boxShadow: "0 0 24px rgba(16, 185, 129, 0.08)" }}
          variants={{
            hidden: { opacity: 0, x: 24 },
            visible: { opacity: 1, x: 0 },
          }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
          aria-labelledby="comparison-refined-heading"
        >
          <h2
            id="comparison-refined-heading"
            className="m-0 mb-4 text-sm font-semibold uppercase tracking-wider text-emerald-400/90"
          >
            Refined Answer
          </h2>
          <div className="text-slate-200 text-base leading-relaxed font-light">
            {formatResponseText(refinedResponse)}
          </div>
        </motion.section>
      </div>

      {showDiff && (
        <motion.section
          className="rounded-2xl p-6 sm:p-8 border border-slate-600"
          style={{ backgroundColor: "#0d0a1a" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
          aria-label="Text differences"
        >
          <h3 className="m-0 mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Text differences
          </h3>
          <div className="text-base leading-relaxed font-light">
            {renderDiff(generatorResponse, refinedResponse, (t) => formatResponseText(t))}
          </div>
        </motion.section>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={() => setShowDiff((v) => !v)}
          className="px-4 py-2 rounded-lg text-sm font-medium text-slate-300 border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition-colors"
        >
          {showDiff ? "Hide text differences" : "Show text differences"}
        </button>
      </div>

      {hasSummary && (
        <motion.section
          className="rounded-2xl p-6 sm:p-8 border border-slate-600"
          style={{ backgroundColor: "#252230" }}
          variants={{
            hidden: { opacity: 0, y: 12 },
            visible: { opacity: 1, y: 0 },
          }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
          aria-labelledby="improvement-summary-heading"
        >
          <h2
            id="improvement-summary-heading"
            className="m-0 mb-5 text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2"
          >
            <span aria-hidden>🔍</span> Improvement summary
          </h2>
          <ul className="list-none m-0 p-0 space-y-2 text-slate-300 text-sm leading-relaxed">
            <li>
              • Reliability: {summary.reliabilityPct}%
            </li>
            <li>
              • Unsupported claims removed: {summary.unsupported}
            </li>
            <li>
              • Verified claims: {summary.supported} / {summary.total}
            </li>
            <li className="text-slate-400 pt-2 border-t border-slate-600/80">
              Clarity enhanced by verification-backed refinement.
            </li>
          </ul>
        </motion.section>
      )}
    </motion.div>
  );
}
