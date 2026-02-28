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

function getStageTimestamp(stage: (typeof TIMELINE_STAGES)[0], responses: StoredResponse[] | null, workflow: WorkflowStatus | null): string | null {
  if (!workflow) return null;
  if (stage.agentType) {
    if (!responses) return null;
    const r = responses.find((x) => x.agent_type === stage.agentType);
    return r ? new Date(r.timestamp).toLocaleString() : null;
  }
  if (stage.minStatus === "PLANNED" && isStatusAtOrPast(workflow.status, "PLANNED") && workflow.created_at) {
    return new Date(workflow.created_at).toLocaleString();
  }
  const st = workflow.stage_timestamps;
  if (st) {
    if (stage.key === "claim_extraction" && st.claims_extracted_at) {
      return new Date(st.claims_extracted_at).toLocaleString();
    }
    if (stage.key === "retrieval" && st.evidence_retrieved_at) {
      return new Date(st.evidence_retrieved_at).toLocaleString();
    }
    if (stage.key === "verification" && st.verified_at) {
      return new Date(st.verified_at).toLocaleString();
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
  return "bg-slate-700 text-slate-400";
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
      setExpandedClaimId((prev) => (prev === claimId ? null : claimId));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load evidence.";
      setError(message);
    }
  };

  const handleToggleClaimExpand = (claimId: number) => {
    setExpandedClaimId((prev) => (prev === claimId ? null : claimId));
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
    timestamp: getStageTimestamp(stage, responses, state.statusDetails ?? null),
  }));

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 min-h-screen">
      <header className="mb-10 pb-8 border-b border-slate-800/80 flex flex-col items-start">
  

        {/* Main Title with Gradient */}
        <h1 className="m-0 mb-4 text-2xl sm:text-4xl font-extrabold tracking-tight text-slate-100 leading-tight">
          Self-Correcting{' '}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-indigo-400 to-purple-400">
            Multi-Agent AI
          </span>
        </h1>

        {/* Description */}
        <p className="m-0 text-slate-400 text-sm sm:text-base leading-relaxed max-w-[54ch]">
          Ask a question for a baseline answer, or run the full pipeline and inspect claims, evidence, and the refinement timeline.
        </p>
        
      </header>

      <main id="main-content" className="grid gap-6" aria-label="Main content">
        <section className="bg-[#0c1222] rounded-xl p-6 border border-slate-800 shadow-lg">
          <h2 className="m-0 mb-4 text-lg font-semibold text-slate-100 flex items-center gap-2 before:content-[''] before:w-1 before:h-5 before:rounded before:bg-gradient-to-b before:from-indigo-500 before:to-cyan-500">
            Ask a Question
          </h2>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label htmlFor="query-input" className="block font-medium text-sm text-slate-100">
              Your question
            </label>
            <textarea
              id="query-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Example: Explain why TCP performs poorly in wireless networks and compare it with QUIC."
              rows={5}
              className="block w-full min-h-[7rem] resize-y px-4 py-3 rounded-md border border-slate-600 bg-slate-900 text-slate-100 text-base font-sans leading-normal placeholder:text-slate-500 hover:border-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-colors"
            />
            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                className="px-4 py-2 rounded-md font-medium text-white bg-gradient-to-br from-indigo-500 to-cyan-500 hover:from-indigo-600 hover:to-cyan-600 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Running..." : "Quick Run"}
              </button>
              <button
                type="button"
                className="px-4 py-2 rounded-md font-medium text-slate-200 bg-transparent border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                onClick={handleStartAsyncWorkflow}
                disabled={isStartingAsync}
              >
                {isStartingAsync ? "Starting..." : "Full Run"}
              </button>
            </div>
          </form>
          {error && (
            <p className="mt-3 px-3 py-2 rounded-md bg-red-500/15 text-red-300 text-sm" role="alert">
              {error}
            </p>
          )}
        </section>

        <section className="bg-[#0c1222] rounded-xl p-6 border border-slate-800 shadow-lg">
          <h2 className="m-0 mb-4 text-lg font-semibold text-slate-100 flex items-center gap-2 before:content-[''] before:w-1 before:h-5 before:rounded before:bg-gradient-to-b before:from-indigo-500 before:to-cyan-500">
            Answer
          </h2>
          {state.answer ? (
            <div className="rounded-md bg-slate-800/50 p-4 border border-slate-700/50">
              <p className="m-0 text-slate-200 leading-relaxed">{formatResponseText(state.answer)}</p>
            </div>
          ) : state.workflowId && currentStatus === "REFINED" ? (
            responses ? (
              <div className="rounded-md bg-slate-800/50 p-4 border border-slate-700/50">
                <p className="m-0 text-slate-200 leading-relaxed">
                  {formatResponseText(responses.find((r) => r.agent_type === "REFINER")?.response_text ?? "Refined answer not available yet.")}
                </p>
              </div>
            ) : (
              <p className="text-slate-500 text-sm italic">
                Waiting for refined answer to be generated...
              </p>
            )
          ) : (
            <p className="text-slate-500 text-sm italic">
              Submit a question for a quick answer, or run the full pipeline to see a verified, refined answer here.
            </p>
          )}
        </section>

        <section className="bg-[#0c1222] rounded-xl p-6 border border-slate-800 shadow-lg">
          <h2 className="m-0 mb-4 text-lg font-semibold text-slate-100 flex items-center gap-2 before:content-[''] before:w-1 before:h-5 before:rounded before:bg-gradient-to-b before:from-indigo-500 before:to-cyan-500">
            Workflow status &amp; timeline
          </h2>
          {state.workflowId ? (
            <>
              <div className="flex flex-wrap gap-4 mb-4">
                <p className="m-0 text-slate-300 text-sm"><strong className="text-slate-200">Workflow ID</strong> {state.workflowId}</p>
                <p className="m-0 text-slate-300 text-sm flex items-center gap-2 flex-wrap">
                  <strong className="text-slate-200">Status</strong>{" "}
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getStatusBadgeClass(currentStatus || "unknown")}`}>
                    {currentStatus || "N/A"}
                  </span>
                  {pollingIntervalRef.current !== null && !TERMINAL_STATES.includes(currentStatus) && (
                    <span className="text-cyan-400/90 text-xs" aria-live="polite">Auto-updating</span>
                  )}
                </p>
              </div>
              {state.statusDetails?.error_message && (
                <div className="mb-4 px-3 py-2 rounded-md bg-red-500/15 text-red-300 text-sm" role="alert">
                  <strong>Error:</strong> {state.statusDetails.error_message}
                </div>
              )}
              <div className="flex flex-wrap gap-2 mb-4">
                <button
                  type="button"
                  className="px-3 py-1.5 rounded text-sm font-medium text-slate-200 border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed"
                  onClick={handleCheckStatus}
                  disabled={isCheckingStatus}
                >
                  {isCheckingStatus ? "Checking..." : "Refresh status"}
                </button>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded text-sm font-medium text-slate-200 border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed"
                  onClick={handleLoadResponses}
                  disabled={isLoadingResponses}
                >
                  {isLoadingResponses ? "Loading..." : "Load stored responses"}
                </button>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded text-sm font-medium text-slate-200 border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed"
                  onClick={handleLoadClaims}
                  disabled={isLoadingClaims}
                >
                  {isLoadingClaims ? "Loading..." : "Load claims"}
                </button>
              </div>
              {pollingIntervalRef.current !== null && !TERMINAL_STATES.includes(currentStatus) && (
                <p className="text-slate-500 text-xs italic mb-4">
                  Timeline and data are automatically updating every 2 seconds
                </p>
              )}
              {state.statusDetails && (
                <div className="mb-4 space-y-1 text-slate-400 text-sm">
                  <p className="m-0"><strong className="text-slate-300">Created at:</strong> {new Date(state.statusDetails.created_at).toLocaleString()}</p>
                  <p className="m-0"><strong className="text-slate-300">Completed at:</strong> {state.statusDetails.completed_at ? new Date(state.statusDetails.completed_at).toLocaleString() : "—"}</p>
                </div>
              )}

              <div className="mb-6">
                <h3 className="mt-4 mb-2 text-base font-semibold text-slate-100">Pipeline timeline</h3>
                <ul className="list-none m-0 p-0 space-y-0" role="list">
                  {timelineStagesWithState.map((stage) => (
                    <li
                      key={stage.key}
                      className={`flex items-center gap-3 py-2 border-b border-slate-800 last:border-b-0 ${stage.completed ? "text-slate-200" : "text-slate-500"} ${stage.failed && !stage.completed ? "text-red-400" : ""}`}
                    >
                      <span
                        className={`shrink-0 w-2 h-2 rounded-full ${stage.completed ? (stage.failed ? "bg-red-500" : "bg-emerald-500") : "bg-slate-600"}`}
                        aria-hidden="true"
                      />
                      <span className="font-medium text-sm">{stage.label}</span>
                      {(stage.timestamp || (stage.completed && !stage.timestamp)) && (
                        <span className="ml-auto text-xs text-slate-500 tabular-nums">
                          {stage.timestamp ?? "—"}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>

              {responses && (
                <div className="mb-6">
                  <h3 className="mt-4 mb-2 text-base font-semibold text-slate-100">Stored responses</h3>
                  {responses.length === 0 ? (
                    <p className="text-slate-500 text-sm italic m-0">No stored responses for this workflow yet.</p>
                  ) : (
                    <ul className="list-none m-0 p-0 space-y-4">
                      {responses.map((item) => (
                        <li key={item.id} className="rounded-md bg-slate-800/40 p-3 border border-slate-700/50">
                          <div className="flex flex-wrap items-center gap-2 mb-2 text-sm text-slate-400">
                            <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-xs font-medium">{item.agent_type}</span>
                            <span>{new Date(item.timestamp).toLocaleString()}</span>
                            {item.model_used && <span className="text-slate-500">Model: {item.model_used}</span>}
                          </div>
                          <div className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap">{formatResponseText(item.response_text)}</div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {claims && (
                <div className="mb-6">
                  <h3 className="mt-4 mb-2 text-base font-semibold text-slate-100">Claim-level explanation</h3>
                  <p className="text-slate-500 text-xs mb-3 m-0">Click a claim to expand evidence and verification score.</p>
                  {claims.length === 0 ? (
                    <p className="text-slate-500 text-sm italic m-0">No claims extracted yet. Run the async pipeline and load claims after CLAIMS_EXTRACTED.</p>
                  ) : (
                    <ul className="list-none m-0 p-0 space-y-3">
                      {claims.map((c) => {
                        const evidence = evidenceByClaim[c.id] ?? [];
                        const isExpanded = expandedClaimId === c.id;
                        const borderClass = getVerificationStatusBorderClass(c.verification_status);
                        const badgeClass = getVerificationStatusBadgeClass(c.verification_status);
                        return (
                          <li key={c.id} className={`rounded-md border-l-4 ${borderClass} bg-slate-800/30 pl-3 pr-3 py-2`}>
                            <button
                              type="button"
                              className="w-full text-left flex flex-wrap items-center gap-2 py-1 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900"
                              onClick={() => handleToggleClaimExpand(c.id)}
                              aria-expanded={isExpanded}
                              aria-controls={`claim-evidence-${c.id}`}
                              id={`claim-toggle-${c.id}`}
                            >
                              <span className="flex-1 min-w-0 text-slate-200 text-sm font-medium">{c.claim_text}</span>
                              <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badgeClass}`}>
                                {c.verification_status ?? "—"}
                              </span>
                              {c.verification_confidence != null && (
                                <span className="shrink-0 text-slate-500 text-xs tabular-nums">
                                  {(c.verification_confidence * 100).toFixed(0)}%
                                </span>
                              )}
                            </button>
                            {c.entities.length > 0 && (
                              <div className="text-slate-500 text-xs mt-1">{c.entities.join(" · ")}</div>
                            )}
                            {c.extraction_confidence != null && (
                              <div className="text-slate-500 text-xs mt-0.5">Extraction confidence: {(c.extraction_confidence * 100).toFixed(0)}%</div>
                            )}
                            {isExpanded && (
                              <div className="mt-3 pt-3 border-t border-slate-700/50" id={`claim-evidence-${c.id}`} aria-labelledby={`claim-toggle-${c.id}`}>
                                {evidence.length === 0 ? (
                                  <p className="text-slate-500 text-sm italic m-0">Loading evidence…</p>
                                ) : (
                                  <ul className="list-none m-0 p-0 space-y-3">
                                    {evidence.map((e) => (
                                      <li key={e.id} className="rounded-md bg-slate-800/50 p-3 border border-slate-700/50">
                                        <div className="text-slate-200 text-sm leading-relaxed mb-2">{formatResponseText(e.snippet)}</div>
                                        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                          {e.is_external && <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-medium">External</span>}
                                          {e.source_url && <span className="truncate max-w-full" title={e.source_url}>{e.source_url}</span>}
                                          {e.retrieval_score != null && <span>score: {e.retrieval_score.toFixed(2)}</span>}
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

              <div className="mt-6 pt-4 border-t border-slate-800">
                <h3 className="mt-0 mb-3 text-base font-semibold text-slate-100">Developer / debug</h3>
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer mb-3">
                  <input
                    type="checkbox"
                    checked={developerMode}
                    onChange={(e) => setDeveloperMode(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-800 text-indigo-500 focus:ring-indigo-500"
                  />
                  Developer mode
                </label>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded text-sm font-medium text-slate-200 border border-slate-600 hover:border-slate-500 hover:bg-slate-800/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-60 disabled:cursor-not-allowed"
                  onClick={handleLoadDebug}
                  disabled={isLoadingDebug}
                >
                  {isLoadingDebug ? "Loading…" : "Load raw JSON"}
                </button>
                {developerMode && debugPayload && (
                  <div className="mt-4">
                    <div className="flex flex-wrap gap-1 mb-2">
                      {(["workflow", "responses", "claims", "verifications"] as const).map((tab) => (
                        <button
                          key={tab}
                          type="button"
                          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                            debugTab === tab
                              ? "bg-indigo-500/30 text-indigo-200 border border-indigo-500/50"
                              : "bg-slate-800/50 text-slate-400 border border-slate-700 hover:bg-slate-700/50 hover:text-slate-300"
                          }`}
                          onClick={() => setDebugTab(tab)}
                        >
                          {tab}
                        </button>
                      ))}
                    </div>
                    <pre className="m-0 p-4 rounded-md bg-slate-900 border border-slate-700 text-slate-300 text-xs overflow-auto max-h-80 font-mono">
                      {debugTab === "workflow" && JSON.stringify(debugPayload.workflow, null, 2)}
                      {debugTab === "responses" && JSON.stringify(debugPayload.responses, null, 2)}
                      {debugTab === "claims" && JSON.stringify(debugPayload.claims, null, 2)}
                      {debugTab === "verifications" && JSON.stringify(debugPayload.verifications, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </>
          ) : (
            <p className="text-slate-500 text-sm italic m-0">Run the full pipeline to see workflow status, timeline, and claim-level evidence here.</p>
          )}
        </section>
      </main>
    </div>
  );
}
