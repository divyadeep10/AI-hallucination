import { FormEvent, Fragment, useEffect, useRef, useState } from "react";
import {
  fetchEvidenceForClaim,
  fetchWorkflowClaims,
  fetchWorkflowDebug,
  fetchWorkflowResponses,
  fetchWorkflowStatus,
  sendQuery,
  startWorkflowAsync,
  Claim,
  Evidence,
  StoredResponse,
  WorkflowDebugPayload,
  WorkflowStatus,
} from "./api";
import { ComparisonView } from "./ComparisonView";

type QueryState = {
  answer: string | null;
  workflowId: number | null;
  status: string | null;
  statusDetails: WorkflowStatus | null;
};

const initialQueryState: QueryState = {
  answer: null,
  workflowId: null,
  status: null,
  statusDetails: null,
};

const WORKFLOW_STATUS_ORDER: string[] = [
  "CREATED",
  "PLANNED",
  "GENERATED",
  "CLAIMS_EXTRACTED",
  "EVIDENCE_RETRIEVED",
  "VERIFIED",
  "CRITIC_REVIEWED",
  "REFINED",
  "COMPLETED",
  "FAILED",
];

const TIMELINE_STAGES: { key: string; label: string; minStatus: string; agentType: string | null }[] = [
  { key: "planner", label: "Planner", minStatus: "PLANNED", agentType: null },
  { key: "generator", label: "Generator", minStatus: "GENERATED", agentType: "GENERATOR" },
  { key: "claim_extraction", label: "Claim extraction", minStatus: "CLAIMS_EXTRACTED", agentType: null },
  { key: "retrieval", label: "Retrieval", minStatus: "EVIDENCE_RETRIEVED", agentType: null },
  { key: "verification", label: "Verification", minStatus: "VERIFIED", agentType: null },
  { key: "critic", label: "Critic", minStatus: "CRITIC_REVIEWED", agentType: "CRITIC" },
  { key: "refiner", label: "Refiner", minStatus: "REFINED", agentType: "REFINER" },
];

function isStatusAtOrPast(current: string, minRequired: string): boolean {
  const ci = WORKFLOW_STATUS_ORDER.indexOf(current);
  const mi = WORKFLOW_STATUS_ORDER.indexOf(minRequired);
  if (ci === -1 || mi === -1) return false;
  return ci >= mi;
}

/**
 * Determine if a stage has completed based on actual stored data rather than just workflow.status.
 * This ensures the timeline accurately reflects what has actually been executed.
 */
function isStageCompleted(
  stage: (typeof TIMELINE_STAGES)[0],
  responses: StoredResponse[] | null,
  claims: Claim[] | null,
  workflow: WorkflowStatus | null
): boolean {
  if (!workflow) return false;
  
  // For agent types that produce responses, check if the response exists
  if (stage.agentType) {
    const hasResponse = responses?.some((r) => r.agent_type === stage.agentType) ?? false;
    return hasResponse;
  }
  
  // For stages without explicit agent types, check workflow status + data existence
  switch (stage.key) {
    case "planner":
      // Planner completes when status reaches PLANNED
      return isStatusAtOrPast(workflow.status, "PLANNED");
    case "claim_extraction":
      // Claim extraction completes when claims exist OR status is at least CLAIMS_EXTRACTED
      return (claims && claims.length > 0) || isStatusAtOrPast(workflow.status, "CLAIMS_EXTRACTED");
    case "retrieval":
      // Retrieval completes when status reaches EVIDENCE_RETRIEVED
      return isStatusAtOrPast(workflow.status, "EVIDENCE_RETRIEVED");
    case "verification":
      // Verification completes when status reaches VERIFIED
      return isStatusAtOrPast(workflow.status, "VERIFIED");
    default:
      return false;
  }
}

function getStageTimestamp(stage: (typeof TIMELINE_STAGES)[0], responses: StoredResponse[] | null, workflow: WorkflowStatus | null, formatDateTimeFn: (s: string | null | undefined) => string): string | null {
  if (!workflow) return null;
  if (stage.agentType) {
    if (!responses) return null;
    const r = responses.find((x) => x.agent_type === stage.agentType);
    return r ? formatDateTimeFn(r.timestamp) : null;
  }
  if (stage.minStatus === "PLANNED" && isStatusAtOrPast(workflow.status, "PLANNED") && workflow.created_at) {
    return formatDateTimeFn(workflow.created_at);
  }
  const st = workflow.stage_timestamps;
  if (st) {
    if (stage.key === "claim_extraction" && st.claims_extracted_at) {
      return formatDateTimeFn(st.claims_extracted_at);
    }
    if (stage.key === "retrieval" && st.evidence_retrieved_at) {
      return formatDateTimeFn(st.evidence_retrieved_at);
    }
    if (stage.key === "verification" && st.verified_at) {
      return formatDateTimeFn(st.verified_at);
    }
  }
  return null;
}

function getVerificationStatusBorderClass(status: string | null | undefined): string {
  if (!status) return "border-l-amber-500";
  const s = (status || "").toUpperCase();
  if (s === "SUPPORTED") return "border-l-emerald-500";
  if (s === "CONTRADICTED") return "border-l-red-500";
  return "border-l-amber-500";
}

function getVerificationStatusBadgeClass(status: string | null | undefined): string {
  if (!status) return "bg-amber-500/20 text-amber-200";
  const s = (status || "").toUpperCase();
  if (s === "SUPPORTED") return "bg-emerald-500/20 text-emerald-300";
  if (s === "CONTRADICTED") return "bg-red-500/20 text-red-300";
  return "bg-amber-500/20 text-amber-200";
}

function getStatusBadgeClass(status: string): string {
  const s = (status || "").toLowerCase();
  if (["completed", "refined", "verified", "critic_reviewed", "evidence_retrieved", "claims_extracted", "generated", "planned", "created"].includes(s))
    return "bg-emerald-500/20 text-emerald-300";
  if (s === "failed") return "bg-red-500/20 text-red-300";
  return "bg-white/10 text-slate-300";
}

/** Format ISO date string to local time; treat missing timezone as UTC so display is correct. */
function formatDateTime(isoStr: string | null | undefined): string {
  if (isoStr == null || isoStr === "") return "—";
  const s = /(Z|[+-]\d{2}:?\d{2})$/.test(isoStr) ? isoStr : isoStr + "Z";
  const date = new Date(s);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

/** Renders text with **bold** and *italic* parsed; newlines preserved. Avoids showing raw asterisks. */
function formatResponseText(text: string): React.ReactNode {
  if (!text) return null;
  const lines = text.split(/\n/);
  return (
    <>
      {lines.map((line, lineIdx) => (
        <Fragment key={lineIdx}>
          {lineIdx > 0 && <br />}
          {parseInlineMarkdown(line, lineIdx)}
        </Fragment>
      ))}
    </>
  );
}

function parseInlineMarkdown(line: string, lineKey: number): React.ReactNode {
  const parts = line.split(/(\*\*|\*)/g);
  const nodes: React.ReactNode[] = [];
  let i = 0;
  while (i < parts.length) {
    if (parts[i] === "**" && i + 2 < parts.length) {
      nodes.push(<strong key={`${lineKey}-${i}`}>{parts[i + 1]}</strong>);
      i += 3;
    } else if (parts[i] === "*" && i + 2 < parts.length && parts[i + 1] !== "*") {
      nodes.push(<em key={`${lineKey}-${i}`}>{parts[i + 1]}</em>);
      i += 3;
    } else {
      nodes.push(parts[i]);
      i += 1;
    }
  }
  return <>{nodes}</>;
}

export function App() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<QueryState>(initialQueryState);
  const [responses, setResponses] = useState<StoredResponse[] | null>(null);
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [evidenceByClaim, setEvidenceByClaim] = useState<Record<number, Evidence[]>>({});
  const [expandedClaimId, setExpandedClaimId] = useState<number | null>(null);
  const [developerMode, setDeveloperMode] = useState(false);
  const [debugPayload, setDebugPayload] = useState<WorkflowDebugPayload | null>(null);
  const [debugTab, setDebugTab] = useState<"workflow" | "responses" | "claims" | "verifications">("workflow");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStartingAsync, setIsStartingAsync] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [isLoadingResponses, setIsLoadingResponses] = useState(false);
  const [isLoadingClaims, setIsLoadingClaims] = useState(false);
  const [isLoadingDebug, setIsLoadingDebug] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Polling state and refs
  const pollingIntervalRef = useRef<number | null>(null);
  const lastPolledStatusRef = useRef<string | null>(null);
  const errorCountRef = useRef<number>(0);
  const isPollingRef = useRef<boolean>(false);
  const resultsSectionRef = useRef<HTMLDivElement>(null);

  // Terminal states that should stop polling
  const TERMINAL_STATES = ["COMPLETED", "FAILED"];
  const POLL_INTERVAL_ACTIVE = 2000; // 2 seconds while active
  const POLL_INTERVAL_TERMINAL = 10000; // 10 seconds when terminal (for final updates)
  const MAX_ERROR_COUNT = 3; // Stop polling after 3 consecutive errors

  // Helper to check if we should poll for responses based on status
  const shouldPollResponses = (status: string): boolean => {
    return isStatusAtOrPast(status, "GENERATED");
  };

  // Helper to check if we should poll for claims based on status
  const shouldPollClaims = (status: string): boolean => {
    return isStatusAtOrPast(status, "CLAIMS_EXTRACTED");
  };

  // Poll workflow status
  const pollStatus = async (workflowId: number): Promise<boolean> => {
    try {
      const statusDetails = await fetchWorkflowStatus(workflowId);
      const newStatus = statusDetails.status;
      
      setState((prev) => ({ ...prev, status: newStatus, statusDetails }));
      lastPolledStatusRef.current = newStatus;
      errorCountRef.current = 0; // Reset error count on success
      
      return true;
    } catch (err) {
      errorCountRef.current += 1;
      if (errorCountRef.current >= MAX_ERROR_COUNT) {
        console.warn(`[Polling] Stopped polling after ${MAX_ERROR_COUNT} consecutive errors`);
        return false;
      }
      return true; // Continue polling on transient errors
    }
  };

  // Poll responses if needed
  const pollResponses = async (workflowId: number): Promise<void> => {
    if (isLoadingResponses) return; // Avoid concurrent requests
    
    try {
      const items = await fetchWorkflowResponses(workflowId);
      setResponses((prev) => {
        // Only update if we got new data (avoid unnecessary re-renders)
        if (!prev || prev.length !== items.length) {
          return items;
        }
        // Check if any response is new or updated
        const hasChanges = items.some((item, idx) => {
          const oldItem = prev[idx];
          return !oldItem || oldItem.id !== item.id || oldItem.response_text !== item.response_text;
        });
        return hasChanges ? items : prev;
      });
    } catch (err) {
      // Silently fail - don't spam errors for responses polling
      console.warn("[Polling] Failed to poll responses:", err);
    }
  };

  // Poll claims if needed
  const pollClaims = async (workflowId: number): Promise<void> => {
    if (isLoadingClaims) return; // Avoid concurrent requests
    
    try {
      const items = await fetchWorkflowClaims(workflowId);
      setClaims((prev) => {
        // Only update if we got new data
        if (!prev || prev.length !== items.length) {
          return items;
        }
        // Check if any claim is new or updated
        const hasChanges = items.some((item, idx) => {
          const oldItem = prev[idx];
          return !oldItem || oldItem.id !== item.id || oldItem.verification_status !== item.verification_status;
        });
        return hasChanges ? items : prev;
      });
    } catch (err) {
      // Silently fail - don't spam errors for claims polling
      console.warn("[Polling] Failed to poll claims:", err);
    }
  };

  // Main polling function
  const performPoll = async (workflowId: number): Promise<void> => {
    if (isPollingRef.current) return; // Prevent concurrent polls
    isPollingRef.current = true;

    try {
      const success = await pollStatus(workflowId);
      if (!success) {
        stopPolling();
        return;
      }

      // Use the status we just fetched (from ref, which was updated in pollStatus)
      const currentStatus = lastPolledStatusRef.current ?? "";
      
      // Poll responses if status indicates they should exist
      if (shouldPollResponses(currentStatus)) {
        await pollResponses(workflowId);
      }

      // Poll claims if status indicates they should exist
      if (shouldPollClaims(currentStatus)) {
        await pollClaims(workflowId);
      }

      // Stop polling if workflow reached terminal state
      if (TERMINAL_STATES.includes(currentStatus)) {
        // Do one final poll after a short delay to catch any final updates
        setTimeout(() => {
          pollStatus(workflowId).catch(() => {});
          pollResponses(workflowId).catch(() => {});
          pollClaims(workflowId).catch(() => {});
        }, 1000);
        stopPolling();
      }
    } finally {
      isPollingRef.current = false;
    }
  };

  // Start polling
  const startPolling = (workflowId: number): void => {
    stopPolling(); // Clear any existing polling

    // Initial poll immediately
    performPoll(workflowId).catch(() => {});

    // Set up interval polling (always use active interval, terminal check happens in performPoll)
    const intervalId = window.setInterval(() => {
      performPoll(workflowId).catch(() => {});
    }, POLL_INTERVAL_ACTIVE);

    pollingIntervalRef.current = intervalId;
  };

  // Stop polling
  const stopPolling = (): void => {
    if (pollingIntervalRef.current !== null) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    isPollingRef.current = false;
  };

  // Auto-polling effect: start/stop based on workflowId
  useEffect(() => {
    if (!state.workflowId) {
      stopPolling();
      return;
    }
    startPolling(state.workflowId);
    return () => {
      stopPolling();
    };
  }, [state.workflowId]);

  // Also stop polling when workflow reaches terminal state (backup check)
  useEffect(() => {
    const currentStatus = state.statusDetails?.status ?? state.status ?? "";
    if (TERMINAL_STATES.includes(currentStatus) && pollingIntervalRef.current !== null) {
      // Give it one more poll cycle to catch final updates, then stop
      const timeoutId = setTimeout(() => {
        stopPolling();
      }, POLL_INTERVAL_ACTIVE + 500);
      return () => clearTimeout(timeoutId);
    }
  }, [state.statusDetails?.status, state.status]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setError("Please enter a question before submitting.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    setState(initialQueryState);
    setResponses(null);
    setClaims(null);
    setEvidenceByClaim({});
    setDebugPayload(null);
    setExpandedClaimId(null);
    try {
      const response = await sendQuery(trimmed);
      setState({
        answer: response.answer,
        workflowId: response.workflow_id,
        status: response.status,
        statusDetails: null,
      });
      // Scroll to results for accessibility
      setTimeout(() => resultsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    } catch (err) {
      const message = err instanceof Error ? err.message : "An unexpected error occurred.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartAsyncWorkflow = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setError("Please enter a question first.");
      return;
    }
    // Stop any existing polling and reset polling state
    stopPolling();
    lastPolledStatusRef.current = null;
    errorCountRef.current = 0;
    
    setIsStartingAsync(true);
    setError(null);
    setState(initialQueryState);
    setResponses(null);
    setClaims(null);
    setEvidenceByClaim({});
    setDebugPayload(null);
    setExpandedClaimId(null);
    try {
      const response = await startWorkflowAsync(trimmed);
      setState({
        answer: null,
        workflowId: response.workflow_id,
        status: response.status,
        statusDetails: response,
      });
      // Scroll to results for accessibility
      setTimeout(() => resultsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      // Polling will automatically start via useEffect when workflowId is set
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to start workflow.";
      setError(message);
    } finally {
      setIsStartingAsync(false);
    }
  };

  const handleCheckStatus = async () => {
    if (!state.workflowId) return;
    setIsCheckingStatus(true);
    setError(null);
    try {
      const statusDetails = await fetchWorkflowStatus(state.workflowId);
      setState((prev) => ({ ...prev, status: statusDetails.status, statusDetails }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch workflow status.";
      setError(message);
    } finally {
      setIsCheckingStatus(false);
    }
  };

  const handleLoadResponses = async () => {
    if (!state.workflowId) return;
    setIsLoadingResponses(true);
    setError(null);
    try {
      const items = await fetchWorkflowResponses(state.workflowId);
      setResponses(items);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load stored responses.";
      setError(message);
    } finally {
      setIsLoadingResponses(false);
    }
  };

  const handleLoadClaims = async () => {
    if (!state.workflowId) return;
    setIsLoadingClaims(true);
    setError(null);
    try {
      const items = await fetchWorkflowClaims(state.workflowId);
      setClaims(items);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load claims.";
      setError(message);
    } finally {
      setIsLoadingClaims(false);
    }
  };

  const handleLoadEvidenceForClaim = async (claimId: number) => {
    setError(null);
    try {
      const items = await fetchEvidenceForClaim(claimId);
      setEvidenceByClaim((prev) => ({ ...prev, [claimId]: items }));
      // Do not toggle expand state here – leave it to the user; keeps panel open when evidence loads
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load evidence.";
      setError(message);
    }
  };

  const handleToggleClaimExpand = (claimId: number, verificationStatus: string | null | undefined) => {
    const nextExpanded = expandedClaimId === claimId ? null : claimId;
    setExpandedClaimId(nextExpanded);
    if (nextExpanded === null) return;
    const isNoEvidence = (verificationStatus ?? "").toUpperCase() === "NO_EVIDENCE";
    if (isNoEvidence) {
      setEvidenceByClaim((prev) => ({ ...prev, [claimId]: [] }));
      return;
    }
    if (!evidenceByClaim[claimId]) {
      handleLoadEvidenceForClaim(claimId);
    }
  };

  const handleLoadDebug = async () => {
    if (!state.workflowId) return;
    setIsLoadingDebug(true);
    setError(null);
    try {
      const payload = await fetchWorkflowDebug(state.workflowId);
      setDebugPayload(payload);
      setDeveloperMode(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load debug data.";
      setError(message);
    } finally {
      setIsLoadingDebug(false);
    }
  };

  const currentStatus = state.statusDetails?.status ?? state.status ?? "";
  const timelineStagesWithState = TIMELINE_STAGES.map((stage) => ({
    ...stage,
    completed: isStageCompleted(stage, responses, claims, state.statusDetails ?? null),
    failed: currentStatus === "FAILED",
    timestamp: getStageTimestamp(stage, responses, state.statusDetails ?? null, formatDateTime),
  }));
  return (
    <>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes blob-morph {
          0%   { border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%; }
          50%  { border-radius: 40% 60% 70% 30% / 50% 60% 30% 60%; }
          100% { border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%; }
        }
        @keyframes blob-spin {
          from { transform: translate(-50%, -50%) rotate(0deg); }
          to   { transform: translate(-50%, -50%) rotate(360deg); }
        }
        .liquid-blob {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 40% 30%, #684cf0 0%, #351c75 40%, #150a29 80%);
          box-shadow: inset 0 20px 60px rgba(255,255,255,0.15), inset 0 -40px 80px rgba(0,0,0,0.8);
          animation: blob-morph 12s ease-in-out infinite, blob-spin 30s linear infinite;
        }
        /* Hide scrollbar for clean UI */
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}} />

      <div className="min-h-screen bg-[#0b0814] relative text-slate-100 font-sans selection:bg-purple-500/30 overflow-x-hidden">
        
        {/* Liquid blob: fixed, centered in viewport using margin (avoids transform conflict with inner animation) */}
        <div
          className="fixed left-1/2 top-1/2 w-[600px] h-[600px] sm:w-[800px] sm:h-[800px] -ml-[300px] -mt-[300px] sm:-ml-[40px] sm:-mt-[40px] z-0 pointer-events-none select-none"
          aria-hidden="true"
        >
          <div className="liquid-blob opacity-90" />
        </div>

        {/* Subtle starry dots overlay for depth */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none -z-20"></div>
        {/* Navigation Bar */}
        <nav className="relative z-50 flex items-center justify-between px-6 sm:px-8 py-6 w-full max-w-7xl mx-auto">
          <div className="text-xl font-bold tracking-tight text-white">
            MultiAgent AI
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm text-slate-300">
            <a href="#" className="hover:text-white transition-colors">About</a>
            <a href="#" className="flex items-center gap-1 hover:text-white transition-colors">Trading <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg></a>
            <a href="#" className="hover:text-white transition-colors">Contact</a>
            <a href="#" className="hover:text-white transition-colors">FAQ</a>
            <a href="#" className="flex items-center gap-1 hover:text-white transition-colors">ENG <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg></a>
          </div>
          <div className="flex items-center gap-4">
            <button className="text-sm font-medium text-slate-300 hover:text-white transition-colors hidden sm:block">Login</button>
            <button className="px-5 py-2 rounded-full text-sm font-medium text-white bg-gradient-to-r from-indigo-500 to-purple-500 hover:opacity-90 transition-opacity shadow-lg shadow-purple-500/20">Sign up</button>
          </div>
        </nav>
        <div className="relative z-10 max-w-5xl mx-auto px-6 pt-24 pb-24 flex flex-col items-center">
          
          {/* Header Section (With positive z-index to stay ABOVE the blob) */}
          <header className="relative z-20 mb-16 flex flex-col items-center text-center">
            <h1 className="m-0 mb-6 text-5xl sm:text-7xl font-extrabold tracking-tight text-white leading-[1.1]">
              Self-Correcting <br className="hidden sm:block"/>
              Multi-Agent AI
            </h1>
            <p className="m-0 text-[#9ba1a6] text-base sm:text-lg leading-relaxed max-w-[60ch]">
              Unlock your knowledge potential in a fully automated environment, powered by multi-agent reasoning. Ask a question to begin.
            </p>
          </header>

          <main id="main-content" className="w-full relative" aria-label="Main content">
            
            {/* Chatbot Form Wrapper */}
            <div className="relative w-full flex justify-center mb-16 pt-10">
              <div className="w-full max-w-2xl relative">
                <form onSubmit={handleSubmit} className="flex flex-col gap-4 relative">
                  <div className="relative group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-purple-500 to-indigo-500 rounded-[2rem] blur opacity-25 group-hover:opacity-40 transition duration-1000 group-hover:duration-200"></div>
                    <div className="relative bg-[#0d0a1a]/80 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] p-2">
                      <textarea
                        id="query-input"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Ask anything... (e.g., Explain why TCP performs poorly in wireless networks)"
                        rows={3}
                        className="block w-full resize-none px-6 py-4 bg-transparent text-white text-lg placeholder:text-slate-400 outline-none focus:ring-0 border-none transition-colors no-scrollbar relative z-40"
                      />
                      <div className="flex flex-wrap items-center justify-end gap-3 px-4 pb-3 pt-2 relative z-40">
                        <button
                          type="button"
                          className="px-6 py-2.5 rounded-full font-medium text-white bg-transparent hover:bg-white/5 border border-transparent hover:border-white/10 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
                          onClick={handleStartAsyncWorkflow}
                          disabled={isStartingAsync}
                        >
                          {isStartingAsync ? "Starting..." : "Full Pipeline Run"}
                        </button>
                        <button
                          type="submit"
                          className="px-8 py-2.5 rounded-full font-semibold text-[#080510] bg-white hover:bg-slate-200 shadow-[0_0_20px_rgba(255,255,255,0.2)] focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-[#080510] disabled:opacity-60 disabled:cursor-not-allowed transition-all"
                          disabled={isSubmitting}
                        >
                          {isSubmitting ? "Running..." : "Quick Run"}
                        </button>
                      </div>
                    </div>
                  </div>
                </form>
                {error && (
                  <div className="mt-6 px-6 py-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm backdrop-blur-md text-center max-w-md mx-auto relative z-30" role="alert">
                    {error}
                  </div>
                )}
              </div>
            </div>

            {/* Content Sections (Output) – scroll target; each section is its own card, no single broad wrapper */}
            <div id="results-section" ref={resultsSectionRef} className="max-w-4xl mx-auto space-y-8 relative z-20 scroll-mt-6">
              
              {/* Post-refinement comparison (when REFINED and both responses exist) or single Response section */}
              {(state.answer || state.workflowId) && (() => {
                const generatorResponse = responses?.find((r) => r.agent_type === "GENERATOR")?.response_text;
                const refinedResponse = responses?.find((r) => r.agent_type === "REFINER")?.response_text;
                const showComparison = currentStatus === "REFINED" && generatorResponse != null && refinedResponse != null && generatorResponse !== "" && refinedResponse !== "";
                if (showComparison) {
                  return (
                    <ComparisonView
                      generatorResponse={generatorResponse}
                      refinedResponse={refinedResponse}
                      claims={claims ?? []}
                      formatResponseText={formatResponseText}
                    />
                  );
                }
                return (
                  <section className="rounded-2xl p-6 sm:p-10 border border-slate-600 shadow-xl" style={{ backgroundColor: "#0d0a1a" }} aria-labelledby="response-heading">
                    <h2 id="response-heading" className="m-0 mb-6 text-xl font-bold tracking-tight text-white flex items-center gap-3">
                      <span className="w-2 h-6 rounded-full bg-gradient-to-b from-purple-400 to-indigo-500" aria-hidden="true"></span>
                      Response
                    </h2>
                    {state.answer ? (
                      <div className="text-slate-200 text-lg leading-relaxed font-light">
                        {formatResponseText(state.answer)}
                      </div>
                    ) : state.workflowId && currentStatus === "REFINED" ? (
                      responses ? (
                        <div className="text-slate-200 text-lg leading-relaxed font-light">
                          {formatResponseText(responses.find((r) => r.agent_type === "REFINER")?.response_text ?? "Refined answer not available yet.")}
                        </div>
                      ) : (
                        <p className="text-slate-400 text-base animate-pulse">
                          Waiting for refined answer to be generated...
                        </p>
                      )
                    ) : (
                      <div className="flex items-center gap-4 text-slate-400 text-base">
                        <div className="w-5 h-5 rounded-full border-2 border-purple-500 border-t-transparent animate-spin"></div>
                        Pipeline active, gathering verified insights...
                      </div>
                    )}
                  </section>
                );
              })()}

              {/* Workflow & Timeline – standalone section */}
              {state.workflowId && (
                <section className="rounded-2xl p-6 sm:p-10 border border-slate-600 shadow-xl" style={{ backgroundColor: "#0d0a1a" }} aria-labelledby="workflow-heading">
                  <h2 id="workflow-heading" className="m-0 mb-8 text-xl font-bold tracking-tight text-white flex items-center gap-3">
                    <span className="w-2 h-6 rounded-full bg-gradient-to-b from-purple-400 to-indigo-500" aria-hidden="true"></span>
                    Workflow & Timeline
                  </h2>
                  
                  {state.statusDetails?.error_message && (
                    <div className="mb-8 px-5 py-4 rounded-xl bg-[#2a1515] border border-red-500/40 text-red-300 text-sm" role="alert">
                      <strong>Error:</strong> {state.statusDetails.error_message}
                    </div>
                  )}
                  
                  {state.statusDetails && (
                    <div className="mb-10 grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 text-sm p-5 sm:p-6 rounded-xl border border-slate-600" style={{ backgroundColor: "#252230" }}>
                      <div className="flex flex-col gap-1">
                        <span className="text-slate-500 text-xs font-medium uppercase tracking-wider">Created</span>
                        <span className="text-slate-200 font-mono text-sm">{formatDateTime(state.statusDetails.created_at)}</span>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-slate-500 text-xs font-medium uppercase tracking-wider">Completed</span>
                        <span className="text-slate-200 font-mono text-sm">{formatDateTime(state.statusDetails.completed_at)}</span>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-slate-500 text-xs font-medium uppercase tracking-wider">Current Status</span>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold ${getStatusBadgeClass(currentStatus || "unknown")}`}>
                            {currentStatus || "N/A"}
                          </span>
                          {pollingIntervalRef.current !== null && !TERMINAL_STATES.includes(currentStatus) && (
                            <span className="flex h-2 w-2 shrink-0 relative overflow-hidden rounded-full" aria-hidden="true">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="mb-12">
                    <h3 className="mt-0 mb-6 text-xs font-bold tracking-widest uppercase text-slate-400">Pipeline Timeline</h3>
                    <ul className="list-none m-0 p-0 relative" role="list" aria-label="Pipeline stages">
                      {timelineStagesWithState.map((stage, index) => {
                        const prevCompleted = index > 0 && timelineStagesWithState[index - 1].completed;
                        const segmentFilled = prevCompleted;
                        const segmentColor = currentStatus === "FAILED" && timelineStagesWithState[index - 1]?.failed
                          ? "#ef4444"
                          : segmentFilled
                            ? "#a855f7"
                            : "#475569";
                        return (
                          <li
                            key={stage.key}
                            className={`relative flex items-center justify-between gap-4 ${stage.completed ? "text-slate-200" : "text-slate-500"} ${stage.failed && !stage.completed ? "text-red-400" : ""}`}
                          >
                            {/* Left: stage label */}
                            <div className="flex-1 min-w-0 pr-5 text-right py-3">
                              <span className="font-semibold text-base text-inherit leading-snug break-words">
                                {stage.label}
                              </span>
                            </div>
                            {/* Center: connector segment (line above dot) + dot */}
                            <div className="flex-shrink-0 w-6 flex flex-col items-center">
                              {/* Line segment between previous dot and this dot – visible and fills on completion */}
                              {index > 0 && (
                                <div
                                  className="w-1 rounded-full flex-shrink-0 transition-colors duration-300"
                                  style={{ height: "1.5rem", backgroundColor: segmentColor }}
                                  aria-hidden="true"
                                />
                              )}
                              <span
                                className={`block w-4 h-4 rounded-full border-2 border-[#211e28] shrink-0 ${stage.completed ? (stage.failed ? "bg-red-500" : "bg-purple-500") : "bg-slate-600"}`}
                                aria-hidden="true"
                              />
                            </div>
                            {/* Right: timestamp */}
                            <div className="flex-1 min-w-0 pl-5 text-left py-3">
                              {(stage.timestamp || (stage.completed && !stage.timestamp)) && (
                                <span className="text-sm text-slate-500 tabular-nums font-mono block break-words">
                                  {stage.timestamp ?? "—"}
                                </span>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  {responses && (
                    <div className="mb-12">
                      <h3 className="mt-0 mb-5 text-xs font-bold tracking-widest uppercase text-slate-400">Stored Responses</h3>
                      {responses.length === 0 ? (
                        <p className="text-slate-500 text-sm italic m-0 p-6 rounded-xl border border-slate-600 text-center" style={{ backgroundColor: "#252230" }}>No stored responses for this workflow yet.</p>
                      ) : (
                        <ul className="list-none m-0 p-0 space-y-4">
                          {responses.map((item) => (
                            <li key={item.id} className="rounded-xl p-6 border border-slate-600 hover:border-slate-500 transition-colors" style={{ backgroundColor: "#252230" }}>
                              <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
                                <span className="px-3 py-1.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20 text-xs font-bold uppercase tracking-wider">{item.agent_type}</span>
                                <span className="text-slate-500 font-mono text-xs">{formatDateTime(item.timestamp)}</span>
                                {item.model_used && <span className="text-slate-500 ml-auto px-3 py-1.5 rounded-full text-[10px] font-mono border border-white/5 uppercase tracking-wider">{item.model_used}</span>}
                              </div>
                              <div className="text-slate-200 text-base leading-relaxed whitespace-pre-wrap font-light">{formatResponseText(item.response_text)}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {claims && (
                    <div className="mb-10">
                      <h3 className="mt-0 mb-6 text-xs font-bold tracking-widest uppercase text-slate-500 flex justify-between items-center">
                        Claim-Level Explanation
                        <span className="text-slate-600 text-[10px] normal-case font-normal italic">Tap to expand evidence</span>
                      </h3>
                      
                      {claims.length === 0 ? (
                        <p className="text-slate-500 text-sm italic m-0 p-6 rounded-xl border border-slate-600 text-center" style={{ backgroundColor: "#252230" }}>No claims extracted yet. Run the async pipeline and load claims after CLAIMS_EXTRACTED.</p>
                      ) : (
                        <ul className="list-none m-0 p-0 space-y-3">
                          {claims.map((c) => {
                            const evidence = evidenceByClaim[c.id] ?? [];
                            const isExpanded = expandedClaimId === c.id;
                            const borderClass = getVerificationStatusBorderClass(c.verification_status);
                            const badgeClass = getVerificationStatusBadgeClass(c.verification_status);
                            
                            return (
                              <li key={c.id} className={`rounded-xl border-l-4 ${borderClass} border-r border-t border-b border-slate-600 transition-colors overflow-hidden`} style={{ backgroundColor: isExpanded ? "#2a2732" : "#252230" }}>
                                <button
                                  type="button"
                                  className="w-full text-left flex flex-col sm:flex-row sm:items-center gap-4 p-5 focus:outline-none"
                                  onClick={() => handleToggleClaimExpand(c.id, c.verification_status)}
                                  aria-expanded={isExpanded}
                                  aria-controls={`claim-evidence-${c.id}`}
                                  id={`claim-toggle-${c.id}`}
                                >
                                  <span className="flex-1 min-w-0 text-slate-200 text-base font-medium leading-relaxed">{c.claim_text}</span>
                                  <div className="flex items-center gap-4 shrink-0">
                                    {c.verification_confidence != null && (
                                      <span className="text-slate-500 text-xs tabular-nums font-mono">
                                        {(c.verification_confidence * 100).toFixed(0)}%
                                      </span>
                                    )}
                                    <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${badgeClass}`}>
                                      {c.verification_status ?? "—"}
                                    </span>
                                  </div>
                                </button>
                                
                                {isExpanded && (
                                  <div className="px-5 pb-5" id={`claim-evidence-${c.id}`} aria-labelledby={`claim-toggle-${c.id}`}>
                                    <div className="flex flex-wrap gap-3 text-[10px] text-slate-500 uppercase tracking-widest mb-5 pt-4 border-t border-white/5">
                                      {c.entities.length > 0 && <span>Tags: {c.entities.join(", ")}</span>}
                                      {c.extraction_confidence != null && <span className="ml-auto">Confidence: {(c.extraction_confidence * 100).toFixed(0)}%</span>}
                                    </div>
                                    
                                    {evidence.length === 0 ? (
                                      <p className="text-slate-500 text-sm m-0 p-4 rounded-xl text-center border border-slate-600" style={{ backgroundColor: "#252230" }}>
                                        {evidenceByClaim[c.id] === undefined && (c.verification_status ?? "").toUpperCase() !== "NO_EVIDENCE"
                                          ? "Loading verification evidence…"
                                          : "No evidence"}
                                      </p>
                                    ) : (
                                      <ul className="list-none m-0 p-0 space-y-3">
                                        {evidence.map((e) => (
                                          <li key={e.id} className="rounded-xl p-4 border border-slate-600" style={{ backgroundColor: "#252230" }}>
                                            <div className="text-slate-200 text-sm leading-relaxed mb-4 font-light">{formatResponseText(e.snippet)}</div>
                                            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                              {e.source && (
                                                <span className={`px-2 py-1 rounded font-medium tracking-wide border ${
                                                  e.source === "wikipedia" ? "border-sky-500/30 text-sky-400 bg-sky-500/10" :
                                                  e.source === "wikidata" ? "border-amber-500/30 text-amber-400 bg-amber-500/10" :
                                                  e.source === "external" ? "border-purple-500/20 text-purple-400 bg-purple-500/5" :
                                                  "border-slate-500/30 text-slate-400 bg-slate-500/10"
                                                }`}>
                                                  {e.source === "internal" ? "Internal" : e.source.charAt(0).toUpperCase() + e.source.slice(1)}
                                                </span>
                                              )}
                                              {!e.source && e.is_external && <span className="px-2 py-1 rounded border border-purple-500/20 text-purple-400 bg-purple-500/5 font-medium tracking-wide">External</span>}
                                              {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer" className="truncate max-w-[200px] sm:max-w-xs hover:text-purple-400 transition-colors" title={e.source_url}>{e.source_url}</a>}
                                            </div>
                                          </li>
                                        ))}
                                      </ul>
                                    )}
                                  </div>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  )}

                  <div className="pt-8 border-t border-white/5">
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="m-0 text-xs font-bold tracking-widest uppercase text-slate-500">Developer Tools</h3>
                      <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer hover:text-slate-200 transition-colors">
                        <input
                          type="checkbox"
                          checked={developerMode}
                          onChange={(e) => setDeveloperMode(e.target.checked)}
                          className="rounded bg-black/50 border-white/20 text-purple-500 focus:ring-purple-500 focus:ring-offset-0 focus:ring-offset-transparent"
                        />
                        Debug Mode
                      </label>
                    </div>
                    
                    {developerMode && (
                      <button
                        type="button"
                        className="px-5 py-2.5 rounded-full text-sm font-medium text-slate-200 bg-white/5 border border-white/10 hover:bg-white/10 focus:outline-none transition-colors mb-6"
                        onClick={handleLoadDebug}
                        disabled={isLoadingDebug}
                      >
                        {isLoadingDebug ? "Loading…" : "Load Raw JSON"}
                      </button>
                    )}
                    
                    {developerMode && debugPayload && (
                      <div className="mt-2">
                        <div className="flex flex-wrap gap-2 mb-4 bg-black/20 p-1.5 rounded-xl inline-flex border border-white/5">
                          {(["workflow", "responses", "claims", "verifications"] as const).map((tab) => (
                            <button
                              key={tab}
                              type="button"
                              className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
                                debugTab === tab
                                  ? "bg-purple-500/20 text-purple-300 shadow-sm"
                                  : "text-slate-500 hover:text-slate-300 hover:bg-white/5"
                              }`}
                              onClick={() => setDebugTab(tab)}
                            >
                              {tab}
                            </button>
                          ))}
                        </div>
                        <div className="rounded-2xl bg-[#0a0614] border border-white/10 overflow-hidden shadow-inner">
                          <pre className="m-0 p-6 text-[#a5d6ff] text-xs overflow-auto max-h-[500px] font-mono scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                            {debugTab === "workflow" && JSON.stringify(debugPayload.workflow, null, 2)}
                            {debugTab === "responses" && JSON.stringify(debugPayload.responses, null, 2)}
                            {debugTab === "claims" && JSON.stringify(debugPayload.claims, null, 2)}
                            {debugTab === "verifications" && JSON.stringify(debugPayload.verifications, null, 2)}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>
          </main>
        </div>
      </div>
    </>
  );
}