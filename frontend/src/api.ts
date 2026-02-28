export type QueryResponse = {
  workflow_id: number;
  answer: string;
  status: string;
};

export type WorkflowStatus = {
  workflow_id: number;
  status: string;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  stage_timestamps?: {
    claims_extracted_at?: string;
    evidence_retrieved_at?: string;
    verified_at?: string;
  } | null;
};

export type StoredResponse = {
  id: number;
  agent_type: string;
  response_text: string;
  model_used: string | null;
  timestamp: string;
};

export type Claim = {
  id: number;
  response_id: number;
  claim_text: string;
  entities: string[];
  extraction_confidence: number | null;
  verification_status?: string | null;
  verification_confidence?: number | null;
};

export type Evidence = {
  id: number;
  claim_id: number;
  source_url: string | null;
  snippet: string;
  retrieval_score: number | null;
};

export type VerificationDebugItem = {
  id: number;
  claim_id: number;
  status: string;
  confidence_score: number | null;
  evidence_id: number | null;
};

export type WorkflowDebugPayload = {
  workflow: WorkflowStatus;
  responses: StoredResponse[];
  claims: Claim[];
  evidence: Evidence[];
  verifications: VerificationDebugItem[];
};

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  "http://127.0.0.1:8001";

function getApiErrorDetail(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : String(e))).join("; ");
  }
  return `Request failed with status ${status}`;
}

export async function sendQuery(query: string): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = getApiErrorDetail(data, response.status);
    throw new Error(detail);
  }

  return data as QueryResponse;
}

export async function startWorkflowAsync(query: string): Promise<WorkflowStatus> {
  const response = await fetch(`${API_BASE_URL}/api/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query.trim() }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as WorkflowStatus;
}

export async function fetchWorkflowStatus(
  workflowId: number,
): Promise<WorkflowStatus> {
  const response = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}`);

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }

  return data as WorkflowStatus;
}

export async function fetchWorkflowResponses(
  workflowId: number,
): Promise<StoredResponse[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/workflows/${workflowId}/responses`,
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }

  return data as StoredResponse[];
}

export async function fetchWorkflowClaims(
  workflowId: number,
): Promise<Claim[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/workflows/${workflowId}/claims`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as Claim[];
}

export async function fetchEvidenceForClaim(
  claimId: number,
): Promise<Evidence[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/claims/${claimId}/evidence`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as Evidence[];
}

export async function fetchWorkflowDebug(
  workflowId: number,
): Promise<WorkflowDebugPayload> {
  const response = await fetch(
    `${API_BASE_URL}/api/workflows/${workflowId}/debug`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as WorkflowDebugPayload;
}

// --- Phase 8: Evaluation ---

export type EvaluationRunSummary = {
  id: number;
  name: string | null;
  mode: string;
  status: string;
  summary_metrics: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
};

export type EvaluationSampleSummary = {
  id: number;
  question: string;
  workflow_id_baseline: number | null;
  workflow_id_system: number | null;
  baseline_answer: string | null;
  system_answer: string | null;
  baseline_status: string | null;
  system_status: string | null;
  metrics: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
};

export type EvaluationRunDetail = {
  id: number;
  name: string | null;
  mode: string;
  status: string;
  summary_metrics: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  samples: EvaluationSampleSummary[];
};

export async function fetchEvaluationRuns(): Promise<EvaluationRunSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/evaluations/runs`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as EvaluationRunSummary[];
}

export async function fetchEvaluationRunDetail(
  runId: number,
): Promise<EvaluationRunDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/evaluations/runs/${runId}`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorDetail(data, response.status));
  }
  return data as EvaluationRunDetail;
}

