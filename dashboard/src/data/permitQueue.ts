import dashboardSnapshot from "./generated/dashboardSnapshot.json"

export type DashboardContractVersion = "permitgraph.dashboard.snapshot.v1"

export type PermitStatus = "approved" | "needs-review" | "blocked"

export type Severity = "critical" | "high" | "medium" | "low"

export type TraceState = "passed" | "review" | "blocked"

export type SavedView = {
  id: string
  label: string
  count: number
}

export type RunMeta = {
  branch: string
  completedAt: string | null
  repo: string
  runId: string
  title: string
}

export type QueueSummary = {
  approvedRepos: number
  blockedRepos: number
  cacheHitRatio: number | null
  cachedTokens: number
  citationCoverage: number
  controls: number
  evalPassRate: number | null
  findings: number
  graphPaths: number
  inputTokens: number
  latestScanFilesIndexed: number | null
  latestScanFindings: number | null
  latestScanStatus: string | null
  modelCalls: number
  needsReviewRepos: number
  passedRepos: number
  repos: number
  totalTokens: number
}

export type ArtifactPreview = {
  content: string
  kind: "json" | "markdown" | "text"
  label: string
  path: string
  sizeBytes: number
  truncated: boolean
}

export type QueueFinding = {
  id: string
  repo: string
  source: string
  branch: string
  runId: string
  status: PermitStatus
  severity: Severity
  rule: string
  title: string
  path: string
  line: number
  capability: string
  confidence: number
  owner: string
  age: string
  summary: string
  evidence: string
  scanner: string
  remediation: string
  artifacts: string[]
  artifactStatus: "available" | "partial" | "missing"
  missingArtifacts: string[]
  traceIds: string[]
  commit: {
    date: string | null
    hash: string | null
    message: string | null
  }
  metrics: {
    cacheHitRatio: number | null
    cachedTokens: number
    citationCheckPassed: boolean
    controls: number
    durationSeconds: number | null
    expectationCheckPassed: boolean
    findings: number
    graphPaths: number
    modelCalls: number
    totalTokens: number
  }
}

export type RepoSnapshot = {
  id: string
  label: string
  source: string
  status: PermitStatus
  latestRunId: string
  runIds: string[]
  commit: QueueFinding["commit"]
  counts: {
    controls: number
    findings: number
    graphPaths: number
  }
}

export type RunSnapshot = {
  id: string
  label: string
  repoId: string
  scope: "validation" | "repo"
  status: PermitStatus
  completedAt: string | null
  artifacts: string[]
  artifactStatus?: "available" | "partial" | "missing"
  metrics:
    | QueueFinding["metrics"]
    | {
        cacheHitRatio: number | null
        cachedTokens: number
        citationCoverage: number
        controls: number
        findings: number
        graphPaths: number
        modelCalls: number
        totalTokens: number
      }
}

export type RunDetail = {
  runId: string
  repoId: string
  rowIds: string[]
  artifactPreviewPaths: string[]
  artifactAvailability: "aggregate" | "available" | "partial" | "missing"
  missingArtifacts: string[]
}

export type DecisionLogEntry = {
  id: string
  label: string
  state: TraceState | PermitStatus
  detail: string
}

export type ProofPack = {
  status: "ready" | "partial" | "missing"
  reason: string
  sourceRunPath: string | null
  includedArtifacts: string[]
  missingArtifacts: string[]
}

export type AgentTraceStep = {
  id: string
  label: string
  state: TraceState
  duration: string
  tool: string
  output: string
}

export type PolicyControl = {
  id: string
  label: string
  state: TraceState
  note: string
}

type DashboardSnapshot = {
  contractVersion: DashboardContractVersion
  generatedAt: string
  selectedRunId: string
  repos: RepoSnapshot[]
  runs: RunSnapshot[]
  runMeta: RunMeta
  summary: QueueSummary
  savedViews: SavedView[]
  findings: QueueFinding[]
  artifactPreviews: Record<string, ArtifactPreview>
  runDetails: Record<string, RunDetail>
  decisionLog: DecisionLogEntry[]
  traceSteps: AgentTraceStep[]
  policyControls: PolicyControl[]
  proofPack: ProofPack
  source: Record<string, string | null>
}

const snapshot = dashboardSnapshot as DashboardSnapshot

export const dashboardContractVersion = snapshot.contractVersion
export const dashboardGeneratedAt = snapshot.generatedAt
export const dashboardSource = snapshot.source
export const selectedRunId = snapshot.selectedRunId
export const repos = snapshot.repos
export const runs = snapshot.runs
export const runMeta = snapshot.runMeta
export const queueSummary = snapshot.summary
export const savedViews = snapshot.savedViews
export const queueFindings = snapshot.findings
export const artifactPreviews = snapshot.artifactPreviews
export const runDetails = snapshot.runDetails
export const decisionLog = snapshot.decisionLog
export const agentTraceSteps = snapshot.traceSteps
export const policyControls = snapshot.policyControls
export const proofPack = snapshot.proofPack
