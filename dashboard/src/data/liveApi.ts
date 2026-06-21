import {
  queueFindings as fallbackFindings,
  repos as fallbackRepos,
  savedViews as fallbackSavedViews,
  type PermitStatus,
  type QueueFinding,
  type RepoSnapshot,
  type SavedView,
  type Severity,
} from "@/data/permitQueue"

export type ApiStatus = "loading" | "live" | "static" | "error"

export type ScanJob = {
  id: string
  repositoryId: string
  repositoryLabel: string
  localPath: string
  branch: string | null
  mode: string
  status: "queued" | "running" | "completed" | "failed" | string
  requestedAt: string | null
  claimedAt: string | null
  completedAt: string | null
  error: string | null
}

export type RunEvent = {
  id: number
  eventName: string
  sequence: number
  occurredAt: string
  payload: Record<string, unknown>
}

export type DashboardData = {
  apiStatus: ApiStatus
  error: string | null
  findings: QueueFinding[]
  generatedAt: string | null
  jobs: ScanJob[]
  repos: RepoSnapshot[]
  savedViews: SavedView[]
}

type SnapshotPayload = {
  generatedAt?: string
  repositories?: ApiRepositoryRow[]
  runs?: ApiRunRow[]
  findings?: ApiFindingRow[]
  jobs?: ApiJobRow[]
}

type ApiRepositoryRow = Record<string, unknown>
type ApiRunRow = Record<string, unknown>
type ApiFindingRow = Record<string, unknown>
type ApiJobRow = Record<string, unknown>

const API_BASE_URL =
  import.meta.env.VITE_AGENT_PERMIT_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8787/api"

export const fallbackDashboardData: DashboardData = {
  apiStatus: "static",
  error: null,
  findings: fallbackFindings,
  generatedAt: null,
  jobs: [],
  repos: fallbackRepos,
  savedViews: fallbackSavedViews,
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const response = await fetch(`${API_BASE_URL}/snapshot`, {
    headers: { accept: "application/json" },
  })
  if (!response.ok) {
    throw new Error(`snapshot request failed: ${response.status}`)
  }
  const payload = (await response.json()) as SnapshotPayload
  return snapshotToDashboardData(payload)
}

export async function queueRepositoryScan(input: {
  branch: string
  label: string
  localPath: string
}): Promise<ScanJob> {
  const response = await fetch(`${API_BASE_URL}/jobs`, {
    body: JSON.stringify({
      branch: input.branch.trim() || null,
      label: input.label.trim() || undefined,
      localPath: input.localPath.trim(),
      mode: "scan",
    }),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    method: "POST",
  })
  const payload = (await response.json()) as {
    error?: string
    job?: Record<string, unknown>
  }
  if (!response.ok || !payload.job) {
    throw new Error(payload.error ?? `queue request failed: ${response.status}`)
  }
  return normalizeJob(payload.job)
}

export async function fetchJobEvents(
  jobId: string,
  afterId = 0,
): Promise<RunEvent[]> {
  const response = await fetch(
    `${API_BASE_URL}/events?jobId=${encodeURIComponent(jobId)}&after=${afterId}`,
    { headers: { accept: "text/event-stream" } },
  )
  if (!response.ok) {
    throw new Error(`events request failed: ${response.status}`)
  }
  return parseSseEvents(await response.text())
}

function snapshotToDashboardData(payload: SnapshotPayload): DashboardData {
  const runs = (payload.runs ?? []).map(normalizeRun)
  const jobs = (payload.jobs ?? []).map(normalizeJob)
  const findings = buildFindings(payload.findings ?? [], runs)
  const repos = buildRepos(payload.repositories ?? [], runs, findings)

  return {
    apiStatus: "live",
    error: null,
    findings,
    generatedAt: payload.generatedAt ?? null,
    jobs,
    repos,
    savedViews: buildSavedViews(findings),
  }
}

function buildFindings(
  rows: ApiFindingRow[],
  runs: NormalizedRun[],
): QueueFinding[] {
  const runRows = new Map(runs.map((run) => [run.runId, run]))
  const findings = rows.map((row, index) => {
    const run = runRows.get(stringValue(row.run_id))
    return findingFromRow(row, run, index)
  })
  const findingRunIds = new Set(findings.map((finding) => finding.runId))
  const cleanRuns = runs
    .filter((run) => run.findingsCount === 0 && !findingRunIds.has(run.runId))
    .map((run, index) => cleanFindingFromRun(run, index))

  return [...findings, ...cleanRuns]
}

function findingFromRow(
  row: ApiFindingRow,
  run: NormalizedRun | undefined,
  index: number,
): QueueFinding {
  const repo = stringValue(row.repository_label, "Repository")
  const rule = stringValue(row.rule_id, "unknown-policy")
  const status = normalizeStatus(row.permit_status ?? row.status)
  const severity = normalizeSeverity(row.severity, status)
  const title = stringValue(row.title, `${repo} requires review`)
  const recommendation = stringValue(
    row.recommendation,
    "Review the evidence and reduce permissions before approving this repository for agent automation.",
  )
  const risk = stringValue(row.risk, title)

  return {
    age: formatDate(row.completed_at ?? run?.completedAt),
    artifactStatus: run?.artifactDir ? "available" : "missing",
    artifacts: run?.artifactDir ? [run.artifactDir] : [],
    branch: stringValue(row.branch ?? run?.branch, "local"),
    capability: capabilityForRule(rule),
    commit: {
      date: null,
      hash: null,
      message: null,
    },
    confidence: status === "approved" ? 100 : 92,
    evidence: risk,
    id: stringValue(row.finding_id, `live-finding-${index + 1}`),
    line: numberValue(row.line_start),
    metrics: metricsFromRow(row, run),
    missingArtifacts: run?.artifactDir ? [] : ["scan artifacts"],
    owner: repo,
    path: stringValue(row.path, run?.artifactDir ?? "scan evidence"),
    remediation: recommendation,
    repo,
    rule,
    runId: stringValue(row.run_id, run?.runId ?? "pending-run"),
    scanner: "deterministic scanner",
    severity,
    source: stringValue(row.local_path ?? run?.localPath, repo),
    status,
    summary: risk,
    title,
    traceIds: [],
  }
}

function cleanFindingFromRun(run: NormalizedRun, index: number): QueueFinding {
  return {
    age: formatDate(run.completedAt),
    artifactStatus: run.artifactDir ? "available" : "missing",
    artifacts: run.artifactDir ? [run.artifactDir] : [],
    branch: run.branch ?? "local",
    capability: "clean scan",
    commit: {
      date: null,
      hash: null,
      message: null,
    },
    confidence: 100,
    evidence: "No configured agent-permit risks were found in this run.",
    id: `${run.runId}-clean-${index + 1}`,
    line: 0,
    metrics: metricsFromRun(run),
    missingArtifacts: run.artifactDir ? [] : ["scan artifacts"],
    owner: run.repositoryLabel,
    path: run.artifactDir || "scan evidence",
    remediation: "Keep evidence attached and rescan when repository permissions or agent tooling changes.",
    repo: run.repositoryLabel,
    rule: "clean-run",
    runId: run.runId,
    scanner: "deterministic scanner",
    severity: "low",
    source: run.localPath,
    status: "approved",
    summary: `${run.repositoryLabel} passed this scan.`,
    title: `${run.repositoryLabel} passed this scan`,
    traceIds: [],
  }
}

function buildRepos(
  rows: ApiRepositoryRow[],
  runs: NormalizedRun[],
  findings: QueueFinding[],
): RepoSnapshot[] {
  const latestRunByRepo = new Map<string, NormalizedRun>()
  for (const run of runs) {
    const current = latestRunByRepo.get(run.repositoryId)
    if (!current || stringValue(run.completedAt) > stringValue(current.completedAt)) {
      latestRunByRepo.set(run.repositoryId, run)
    }
  }

  return rows.map((row) => {
    const id = stringValue(row.id)
    const run = latestRunByRepo.get(id)
    const repoFindings = findings.filter((finding) => finding.repo === stringValue(row.label))
    const status = run?.status ?? summarizeStatus(repoFindings)

    return {
      commit: {
        date: null,
        hash: null,
        message: null,
      },
      counts: {
        controls: run?.controlsCount ?? 0,
        findings: repoFindings.filter((finding) => finding.rule !== "clean-run").length,
        graphPaths: run?.graphPathsCount ?? 0,
      },
      id,
      label: stringValue(row.label, "Repository"),
      latestRunId: run?.runId ?? "",
      runIds: runs
        .filter((candidate) => candidate.repositoryId === id)
        .map((candidate) => candidate.runId),
      source: stringValue(row.local_path, ""),
      status,
    }
  })
}

function buildSavedViews(findings: QueueFinding[]): SavedView[] {
  return [
    { count: findings.length, id: "all", label: "All results" },
    {
      count: findings.filter((finding) => finding.status === "blocked").length,
      id: "blocked",
      label: "Blocked",
    },
    {
      count: findings.filter((finding) => finding.status === "needs-review").length,
      id: "needs-review",
      label: "Needs review",
    },
    {
      count: findings.filter((finding) => finding.status === "approved").length,
      id: "approved",
      label: "Approved",
    },
  ]
}

function parseSseEvents(text: string): RunEvent[] {
  return text
    .split(/\n\n+/)
    .map((block) => {
      const lines = block.split("\n")
      const idLine = lines.find((line) => line.startsWith("id: "))
      const eventLine = lines.find((line) => line.startsWith("event: "))
      const dataLine = lines.find((line) => line.startsWith("data: "))
      if (!idLine || !eventLine || !dataLine) return null
      const data = JSON.parse(dataLine.replace(/^data: /, "")) as Record<string, unknown>
      return {
        eventName: eventLine.replace(/^event: /, ""),
        id: Number(idLine.replace(/^id: /, "")),
        occurredAt: stringValue(data.occurred_at),
        payload: objectValue(data.payload_json),
        sequence: numberValue(data.sequence),
      }
    })
    .filter((event): event is RunEvent => event !== null)
}

type NormalizedRun = {
  artifactDir: string
  branch: string | null
  completedAt: string | null
  controlsCount: number
  findingsCount: number
  graphPathsCount: number
  localPath: string
  permitStatus: PermitStatus
  repositoryId: string
  repositoryLabel: string
  runId: string
  status: PermitStatus
}

function normalizeRun(row: ApiRunRow): NormalizedRun {
  const permitStatus = normalizeStatus(row.permit_status)
  return {
    artifactDir: stringValue(row.artifact_dir),
    branch: nullableString(row.branch),
    completedAt: nullableString(row.completed_at),
    controlsCount: numberValue(row.controls_count),
    findingsCount: numberValue(row.findings_count),
    graphPathsCount: numberValue(row.graph_paths_count),
    localPath: stringValue(row.local_path),
    permitStatus,
    repositoryId: stringValue(row.repository_id),
    repositoryLabel: stringValue(row.repository_label, "Repository"),
    runId: stringValue(row.run_id),
    status: permitStatus,
  }
}

function normalizeJob(row: Record<string, unknown>): ScanJob {
  return {
    branch: nullableString(row.branch),
    claimedAt: nullableString(row.claimed_at),
    completedAt: nullableString(row.completed_at),
    error: nullableString(row.error),
    id: stringValue(row.id),
    localPath: stringValue(row.local_path),
    mode: stringValue(row.mode, "scan"),
    repositoryId: stringValue(row.repository_id),
    repositoryLabel: stringValue(row.repository_label, "Repository"),
    requestedAt: nullableString(row.requested_at),
    status: stringValue(row.status, "queued"),
  }
}

function metricsFromRow(
  row: ApiFindingRow,
  run: NormalizedRun | undefined,
): QueueFinding["metrics"] {
  return {
    cacheHitRatio: null,
    cachedTokens: 0,
    citationCheckPassed: true,
    controls: numberValue(row.controls_count, run?.controlsCount ?? 0),
    durationSeconds: null,
    expectationCheckPassed: true,
    findings: numberValue(row.findings_count, run?.findingsCount ?? 1),
    graphPaths: numberValue(row.graph_paths_count, run?.graphPathsCount ?? 0),
    modelCalls: 0,
    totalTokens: 0,
  }
}

function metricsFromRun(run: NormalizedRun): QueueFinding["metrics"] {
  return {
    cacheHitRatio: null,
    cachedTokens: 0,
    citationCheckPassed: true,
    controls: run.controlsCount,
    durationSeconds: null,
    expectationCheckPassed: true,
    findings: run.findingsCount,
    graphPaths: run.graphPathsCount,
    modelCalls: 0,
    totalTokens: 0,
  }
}

function normalizeStatus(value: unknown): PermitStatus {
  const status = stringValue(value).replace("_", "-")
  if (status === "blocked") return "blocked"
  if (status === "approved") return "approved"
  return "needs-review"
}

function normalizeSeverity(value: unknown, status: PermitStatus): Severity {
  const severity = stringValue(value).toLowerCase()
  if (severity === "critical") return "critical"
  if (severity === "high") return "high"
  if (severity === "medium") return "medium"
  if (severity === "low") return "low"
  if (status === "blocked") return "critical"
  if (status === "needs-review") return "high"
  return "low"
}

function summarizeStatus(findings: QueueFinding[]): PermitStatus {
  if (findings.some((finding) => finding.status === "blocked")) return "blocked"
  if (findings.some((finding) => finding.status === "needs-review")) {
    return "needs-review"
  }
  return "approved"
}

function capabilityForRule(rule: string): string {
  if (rule.includes("ci")) return "ci trust boundary"
  if (rule.includes("secret")) return "secret exposure"
  if (rule.includes("mcp")) return "tool access"
  return "repository policy"
}

function formatDate(value: unknown): string {
  const dateValue = stringValue(value)
  if (!dateValue) return "Pending"
  const parsed = new Date(dateValue)
  if (Number.isNaN(parsed.getTime())) return dateValue
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  })
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function numberValue(value: unknown, fallback = 0): number {
  const numeric = typeof value === "number" ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}
