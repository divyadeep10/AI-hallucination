import { FormEvent, useEffect, useRef, useState } from "react";
import {
  fetchEvidenceForClaim,
  fetchEvaluationRunDetail,
  fetchEvaluationRuns,
  fetchWorkflowClaims,
  fetchWorkflowDebug,
  fetchWorkflowResponses,
  fetchWorkflowStatus,
  sendQuery,
  startWorkflowAsync,
  Claim,
  Evidence,
  EvaluationRunDetail,
  EvaluationRunSummary,
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

function getVerificationStatusClass(status: string | null | undefined): string {
  if (!status) return "claim-status-none";
  const s = (status || "").toUpperCase();
  if (s === "SUPPORTED") return "claim-status-supported";
  if (s === "CONTRADICTED") return "claim-status-contradicted";
  if (s === "UNCERTAIN" || s === "NO_EVIDENCE") return "claim-status-uncertain";
  return "claim-status-none";
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
  // Phase 8: Evaluation view
  const [activeView, setActiveView] = useState<"query" | "evaluation">("query");
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRunSummary[] | null>(null);
  const [evaluationRunDetail, setEvaluationRunDetail] = useState<EvaluationRunDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isLoadingRunDetail, setIsLoadingRunDetail] = useState(false);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);

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

  // Auto-polling effect: start/stop based on workflowId and view
  useEffect(() => {
    // Only poll in query view
    if (activeView !== "query") {
      stopPolling();
      return;
    }

    // Only poll if we have an active workflow
    if (!state.workflowId) {
      stopPolling();
      return;
    }

    // Start polling
    startPolling(state.workflowId);

    // Cleanup on unmount or when dependencies change
    return () => {
      stopPolling();
    };
  }, [state.workflowId, activeView]);

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

  useEffect(() => {
    if (activeView !== "evaluation") return;
    setIsLoadingRuns(true);
    setEvaluationError(null);
    fetchEvaluationRuns()
      .then(setEvaluationRuns)
      .catch((err) => setEvaluationError(err instanceof Error ? err.message : "Failed to load runs"))
      .finally(() => setIsLoadingRuns(false));
  }, [activeView]);

  useEffect(() => {
    if (selectedRunId == null) {
      setEvaluationRunDetail(null);
      return;
    }
    setIsLoadingRunDetail(true);
    setEvaluationError(null);
    fetchEvaluationRunDetail(selectedRunId)
      .then(setEvaluationRunDetail)
      .catch((err) => setEvaluationError(err instanceof Error ? err.message : "Failed to load run detail"))
      .finally(() => setIsLoadingRunDetail(false));
  }, [selectedRunId]);

  const currentStatus = state.statusDetails?.status ?? state.status ?? "";
  const timelineStagesWithState = TIMELINE_STAGES.map((stage) => ({
    ...stage,
    completed: isStageCompleted(stage, responses, claims, state.statusDetails ?? null),
    failed: currentStatus === "FAILED",
    timestamp: getStageTimestamp(stage, responses, state.statusDetails ?? null),
  }));

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>Self-Correcting Multi-Agent AI</h1>
        <p>
          Ask a question for a baseline answer, or run the full pipeline (Planner → Generator → Claims → Retrieval → Verification → Critic → Refiner) and inspect the transparency dashboard.
        </p>
        <nav className="app-nav" aria-label="Main">
          <button
            type="button"
            className={`nav-tab ${activeView === "query" ? "active" : ""}`}
            onClick={() => setActiveView("query")}
          >
            Query
          </button>
          <button
            type="button"
            className={`nav-tab ${activeView === "evaluation" ? "active" : ""}`}
            onClick={() => setActiveView("evaluation")}
          >
            Evaluation
          </button>
        </nav>
      </header>

      <main className="app-main">
        {activeView === "evaluation" ? (
          <EvaluationView
            runs={evaluationRuns}
            runDetail={evaluationRunDetail}
            selectedRunId={selectedRunId}
            onSelectRun={setSelectedRunId}
            isLoadingRuns={isLoadingRuns}
            isLoadingRunDetail={isLoadingRunDetail}
            error={evaluationError}
          />
        ) : (
          <>
        <section className="card">
          <h2>Ask a Question</h2>
          <form onSubmit={handleSubmit} className="query-form">
            <label htmlFor="query-input">Your question</label>
            <textarea
              id="query-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Example: Explain why TCP performs poorly in wireless networks and compare it with QUIC."
              rows={5}
            />
            <div className="query-actions">
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Submitting..." : "Submit (baseline)"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={handleStartAsyncWorkflow}
                disabled={isStartingAsync}
              >
                {isStartingAsync ? "Starting..." : "Run full pipeline (async)"}
              </button>
            </div>
          </form>
          {error && <p className="error-message">{error}</p>}
        </section>

        <section className="card">
          <h2>Answer</h2>
          {state.answer ? (
            <div className="answer-block">
              <p>{state.answer}</p>
            </div>
          ) : state.workflowId && currentStatus === "REFINED" ? (
            responses ? (
              <div className="answer-block">
                <p>
                  {responses.find((r) => r.agent_type === "REFINER")?.response_text ?? "Refined answer not available yet."}
                </p>
              </div>
            ) : (
              <p className="placeholder">
                Waiting for refined answer to be generated...
              </p>
            )
          ) : (
            <p className="placeholder">
              Submit a question (baseline) or run full pipeline and load responses to see the answer.
            </p>
          )}
        </section>

        <section className="card">
          <h2>Workflow status &amp; timeline</h2>
          {state.workflowId ? (
            <>
              <p><strong>Workflow ID:</strong> {state.workflowId}</p>
              <p>
                <strong>Current status:</strong>{" "}
                <span className={`status-badge status-${(currentStatus || "unknown").toLowerCase()}`}>
                  {currentStatus || "N/A"}
                </span>
                {pollingIntervalRef.current !== null && !TERMINAL_STATES.includes(currentStatus) && (
                  <span style={{ marginLeft: "0.5rem", fontSize: "0.875rem", color: "#28a745" }}>
                    ● Auto-updating
                  </span>
                )}
              </p>
              {state.statusDetails?.error_message && (
                <div className="error-message" style={{ marginTop: "0.5rem", padding: "0.75rem", backgroundColor: "#fff3cd", border: "1px solid #ffc107", borderRadius: "4px" }}>
                  <strong>Error:</strong> {state.statusDetails.error_message}
                </div>
              )}
              <div className="status-actions">
                <button type="button" onClick={handleCheckStatus} disabled={isCheckingStatus}>
                  {isCheckingStatus ? "Checking..." : "Refresh status"}
                </button>
                <button type="button" onClick={handleLoadResponses} disabled={isLoadingResponses}>
                  {isLoadingResponses ? "Loading..." : "Load stored responses"}
                </button>
                <button type="button" onClick={handleLoadClaims} disabled={isLoadingClaims}>
                  {isLoadingClaims ? "Loading..." : "Load claims"}
                </button>
              </div>
              {pollingIntervalRef.current !== null && !TERMINAL_STATES.includes(currentStatus) && (
                <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", color: "#6c757d", fontStyle: "italic" }}>
                  Timeline and data are automatically updating every 2 seconds
                </p>
              )}
              {state.statusDetails && (
                <div className="status-details">
                  <p><strong>Created at:</strong> {new Date(state.statusDetails.created_at).toLocaleString()}</p>
                  <p><strong>Completed at:</strong> {state.statusDetails.completed_at ? new Date(state.statusDetails.completed_at).toLocaleString() : "—"}</p>
                </div>
              )}

              <div className="timeline-section">
                <h3>Pipeline timeline</h3>
                <ul className="timeline-list">
                  {timelineStagesWithState.map((stage) => (
                    <li
                      key={stage.key}
                      className={`timeline-item ${stage.completed ? "completed" : "pending"} ${stage.failed && !stage.completed ? "failed" : ""}`}
                    >
                      <span className="timeline-marker" aria-hidden />
                      <span className="timeline-label">{stage.label}</span>
                      {stage.timestamp && <span className="timeline-time">{stage.timestamp}</span>}
                      {!stage.timestamp && stage.completed && <span className="timeline-time">—</span>}
                    </li>
                  ))}
                </ul>
              </div>

              {responses && (
                <div className="responses-list">
                  <h3>Stored responses</h3>
                  {responses.length === 0 ? (
                    <p className="placeholder">No stored responses for this workflow yet.</p>
                  ) : (
                    <ul>
                      {responses.map((item) => (
                        <li key={item.id}>
                          <div className="response-meta">
                            <span className="badge">{item.agent_type}</span>
                            <span>{new Date(item.timestamp).toLocaleString()}</span>
                            {item.model_used && <span className="model-used">Model: {item.model_used}</span>}
                          </div>
                          <div className="response-text">{item.response_text}</div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {claims && (
                <div className="claims-list">
                  <h3>Claim-level explanation</h3>
                  <p className="claims-hint">Click a claim to expand evidence and verification score.</p>
                  {claims.length === 0 ? (
                    <p className="placeholder">No claims extracted yet. Run the async pipeline and load claims after CLAIMS_EXTRACTED.</p>
                  ) : (
                    <ul>
                      {claims.map((c) => {
                        const evidence = evidenceByClaim[c.id] ?? [];
                        const isExpanded = expandedClaimId === c.id;
                        const statusClass = getVerificationStatusClass(c.verification_status);
                        return (
                          <li key={c.id} className={`claim-item ${statusClass}`}>
                            <button
                              type="button"
                              className="claim-row"
                              onClick={() => handleToggleClaimExpand(c.id)}
                              aria-expanded={isExpanded}
                            >
                              <span className="claim-text">{c.claim_text}</span>
                              <span className={`claim-status-badge ${statusClass}`}>
                                {c.verification_status ?? "—"}
                              </span>
                              {c.verification_confidence != null && (
                                <span className="claim-verification-score">
                                  {(c.verification_confidence * 100).toFixed(0)}%
                                </span>
                              )}
                            </button>
                            {c.entities.length > 0 && (
                              <div className="claim-entities">{c.entities.join(" · ")}</div>
                            )}
                            {c.extraction_confidence != null && (
                              <div className="claim-confidence">Extraction confidence: {(c.extraction_confidence * 100).toFixed(0)}%</div>
                            )}
                            {isExpanded && (
                              <div className="claim-evidence-block">
                                {evidence.length === 0 ? (
                                  <p className="placeholder">Loading evidence…</p>
                                ) : (
                                  <ul className="evidence-list">
                                    {evidence.map((e) => (
                                      <li key={e.id}>
                                        <div className="evidence-snippet">{e.snippet}</div>
                                        <div className="evidence-meta">
                                          {e.is_external && <span className="evidence-badge external">External</span>}
                                          {e.source_url && <span className="evidence-source">{e.source_url}</span>}
                                          {e.retrieval_score != null && <span className="evidence-score">score: {e.retrieval_score.toFixed(2)}</span>}
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

              <div className="developer-section">
                <h3>Developer / debug</h3>
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={developerMode}
                    onChange={(e) => setDeveloperMode(e.target.checked)}
                  />
                  Developer mode
                </label>
                <button
                  type="button"
                  className="small-button"
                  onClick={handleLoadDebug}
                  disabled={isLoadingDebug}
                >
                  {isLoadingDebug ? "Loading…" : "Load raw JSON"}
                </button>
                {developerMode && debugPayload && (
                  <div className="debug-views">
                    <div className="debug-tabs">
                      {(["workflow", "responses", "claims", "verifications"] as const).map((tab) => (
                        <button
                          key={tab}
                          type="button"
                          className={`debug-tab ${debugTab === tab ? "active" : ""}`}
                          onClick={() => setDebugTab(tab)}
                        >
                          {tab}
                        </button>
                      ))}
                    </div>
                    <pre className="debug-json">
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
            <p className="placeholder">Submit a question or run the full pipeline to see workflow and timeline.</p>
          )}
        </section>
          </>
        )}
      </main>
    </div>
  );
}

function EvaluationView({
  runs,
  runDetail,
  selectedRunId,
  onSelectRun,
  isLoadingRuns,
  isLoadingRunDetail,
  error,
}: {
  runs: EvaluationRunSummary[] | null;
  runDetail: EvaluationRunDetail | null;
  selectedRunId: number | null;
  onSelectRun: (id: number | null) => void;
  isLoadingRuns: boolean;
  isLoadingRunDetail: boolean;
  error: string | null;
}) {
  const m = runDetail?.summary_metrics;
  return (
    <>
      <section className="card">
        <h2>Evaluation runs</h2>
        {error && <p className="error-message">{error}</p>}
        {isLoadingRuns ? (
          <p className="placeholder">Loading runs…</p>
        ) : !runs?.length ? (
          <p className="placeholder">No evaluation runs yet. Run the script: <code>python scripts/run_evaluation.py --dataset data/eval_questions.json --mode both</code></p>
        ) : (
          <ul className="evaluation-runs-list">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={`evaluation-run-item ${selectedRunId === r.id ? "selected" : ""}`}
                  onClick={() => onSelectRun(selectedRunId === r.id ? null : r.id)}
                >
                  <span className="run-id">Run #{r.id}</span>
                  {r.name && <span className="run-name">{r.name}</span>}
                  <span className="run-mode">{r.mode}</span>
                  <span className={`run-status run-status-${r.status}`}>{r.status}</span>
                  <span className="run-date">{new Date(r.created_at).toLocaleString()}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {selectedRunId != null && (
        <section className="card">
          <h2>Run summary</h2>
          {isLoadingRunDetail ? (
            <p className="placeholder">Loading run detail…</p>
          ) : runDetail ? (
            <>
              <div className="eval-metrics-grid">
                {m && (
                  <>
                    <div className="metric-card">
                      <span className="metric-label">Questions</span>
                      <span className="metric-value">{Number(m.num_questions) ?? 0}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Baseline success</span>
                      <span className="metric-value">{Number(m.num_baseline_success) ?? 0}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">System success</span>
                      <span className="metric-value">{Number(m.num_system_success) ?? 0}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Claim verification accuracy</span>
                      <span className="metric-value">{typeof m.avg_claim_verification_accuracy === "number" ? `${(m.avg_claim_verification_accuracy * 100).toFixed(1)}%` : "—"}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">F1 (verification)</span>
                      <span className="metric-value">{typeof m.f1 === "number" ? m.f1.toFixed(3) : "—"}</span>
                    </div>
                  </>
                )}
              </div>
              {m && (Number(m.num_questions) ?? 0) > 0 && (
                <div className="eval-bars">
                  <div className="eval-bar-row">
                    <span className="eval-bar-label">Baseline success rate</span>
                    <div className="eval-bar-track">
                      <div
                        className="eval-bar-fill baseline"
                        style={{ width: `${((Number(m.num_baseline_success) ?? 0) / (Number(m.num_questions) ?? 1)) * 100}%` }}
                      />
                    </div>
                    <span className="eval-bar-pct">{((Number(m.num_baseline_success) ?? 0) / (Number(m.num_questions) ?? 1) * 100).toFixed(0)}%</span>
                  </div>
                  <div className="eval-bar-row">
                    <span className="eval-bar-label">System success rate</span>
                    <div className="eval-bar-track">
                      <div
                        className="eval-bar-fill system"
                        style={{ width: `${((Number(m.num_system_success) ?? 0) / (Number(m.num_questions) ?? 1)) * 100}%` }}
                      />
                    </div>
                    <span className="eval-bar-pct">{((Number(m.num_system_success) ?? 0) / (Number(m.num_questions) ?? 1) * 100).toFixed(0)}%</span>
                  </div>
                  {typeof m.avg_claim_verification_accuracy === "number" && (
                    <div className="eval-bar-row">
                      <span className="eval-bar-label">Claim verification accuracy</span>
                      <div className="eval-bar-track">
                        <div
                          className="eval-bar-fill accuracy"
                          style={{ width: `${m.avg_claim_verification_accuracy * 100}%` }}
                        />
                      </div>
                      <span className="eval-bar-pct">{(m.avg_claim_verification_accuracy * 100).toFixed(0)}%</span>
                    </div>
                  )}
                </div>
              )}
              <h3>Samples</h3>
              <div className="eval-samples-table-wrap">
                <table className="eval-samples-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Question</th>
                      <th>Baseline</th>
                      <th>System</th>
                      <th>Claims / Supported</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runDetail.samples.map((s, idx) => {
                      const sm = s.metrics || {};
                      const numClaims = Number(sm.num_claims) ?? 0;
                      const numSupported = Number(sm.num_supported) ?? 0;
                      return (
                        <tr key={s.id}>
                          <td>{idx + 1}</td>
                          <td className="cell-question">{s.question}</td>
                          <td>{s.baseline_status ?? "—"}</td>
                          <td>{s.system_status ?? "—"}</td>
                          <td>{numClaims > 0 ? `${numSupported}/${numClaims}` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </section>
      )}
    </>
  );
}
