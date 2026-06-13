import { useMemo, useState } from "react"
import {
  ArchiveBoxIcon,
  ArrowSquareOutIcon,
  CheckCircleIcon,
  DatabaseIcon,
  DownloadSimpleIcon,
  FileSearchIcon,
  FlowArrowIcon,
  LockKeyIcon,
  MagnifyingGlassIcon,
  MoonIcon,
  RobotIcon,
  ShieldCheckIcon,
  SunIcon,
  WarningDiamondIcon,
  XCircleIcon,
} from "@phosphor-icons/react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import {
  agentTraceSteps,
  artifactPreviews,
  repos,
  policyControls,
  queueFindings,
  queueSummary,
  runMeta,
  runDetails,
  runs,
  savedViews,
  selectedRunId as defaultSelectedRunId,
  type AgentTraceStep,
  type ArtifactPreview,
  type PermitStatus,
  type QueueSummary,
  type QueueFinding,
  type RepoSnapshot,
  type RunDetail,
  type RunSnapshot,
  type Severity,
  type TraceState,
} from "@/data/permitQueue"

const statusLabels: Record<PermitStatus, string> = {
  approved: "Approved",
  "needs-review": "Needs review",
  blocked: "Blocked",
}

const severityLabels: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
}

const traceLabels: Record<TraceState, string> = {
  passed: "Passed",
  review: "Review",
  blocked: "Blocked",
}

function formatPercent(value: number | null) {
  if (value === null) {
    return "n/a"
  }
  return `${Math.round(value * 100)}%`
}

function formatCompact(value: number) {
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: 1,
    notation: "compact",
  }).format(value)
}

function evidenceLocation(finding: QueueFinding) {
  return finding.line > 0 ? `${finding.path}:${finding.line}` : finding.path
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${Math.round(bytes / 1024)} KB`
}

function artifactAvailabilityLabel(availability: RunDetail["artifactAvailability"]) {
  switch (availability) {
    case "available":
      return "Artifacts ready"
    case "partial":
      return "Partial artifacts"
    case "missing":
      return "Artifacts missing"
    case "aggregate":
      return "Aggregate evidence"
  }
}

function artifactLabel(artifact: string) {
  if (artifact.startsWith("http")) {
    return "External source"
  }
  return artifact.split("/").at(-1) ?? artifact
}

function repoById(repoId: string) {
  return repos.find((repo) => repo.id === repoId)
}

function runById(runId: string) {
  return runs.find((run) => run.id === runId)
}

function runOptionsForRepo(repo: RepoSnapshot | null) {
  if (!repo) {
    return runs.filter((run) => run.repoId === "all")
  }
  return repo.runIds.map((runId) => runById(runId)).filter((run) => run !== undefined)
}

function rowsForRun(detail: RunDetail | undefined) {
  if (!detail) {
    return queueFindings
  }

  const rowIds = new Set(detail.rowIds)
  return queueFindings.filter((row) => rowIds.has(row.id))
}

function summaryForRun(run: RunSnapshot | undefined) {
  if (!run || run.scope === "validation") {
    return queueSummary
  }

  const metrics = run.metrics
  const hasRepoMetrics = "citationCheckPassed" in metrics
  const citationCoverage = hasRepoMetrics
    ? metrics.citationCheckPassed
      ? 1
      : 0
    : "citationCoverage" in metrics
      ? metrics.citationCoverage
      : queueSummary.citationCoverage
  const evalPassRate = hasRepoMetrics
    ? metrics.expectationCheckPassed
      ? 1
      : 0
    : queueSummary.evalPassRate

  return {
    ...queueSummary,
    approvedRepos: run.status === "approved" ? 1 : 0,
    blockedRepos: run.status === "blocked" ? 1 : 0,
    cacheHitRatio: metrics.cacheHitRatio,
    cachedTokens: metrics.cachedTokens,
    citationCoverage,
    controls: metrics.controls,
    evalPassRate,
    findings: metrics.findings,
    graphPaths: metrics.graphPaths,
    inputTokens: Math.max(metrics.totalTokens - metrics.cachedTokens, 0),
    latestScanFilesIndexed: null,
    latestScanFindings: metrics.findings,
    latestScanStatus: run.status,
    modelCalls: metrics.modelCalls,
    needsReviewRepos: run.status === "needs-review" ? 1 : 0,
    passedRepos: run.status === "approved" ? 1 : 0,
    repos: 1,
    totalTokens: metrics.totalTokens,
  } satisfies QueueSummary
}

function verdictCopy(summary: QueueSummary) {
  if (summary.blockedRepos > 0) {
    return {
      action: "Fix blocked CI trust paths first",
      body: `${summary.blockedRepos} repo is blocked. ${summary.findings} findings and ${summary.graphPaths} graph paths need review before this scope should pass unattended.`,
      label: "Run verdict",
      status: "Blocked",
      tone: "blocked",
    }
  }
  if (summary.needsReviewRepos > 0) {
    return {
      action: "Review permit exceptions",
      body: `${summary.needsReviewRepos} repo${summary.needsReviewRepos === 1 ? "" : "s"} need human review. Citation checks passed, but owner approval is still required.`,
      label: "Run verdict",
      status: "Needs review",
      tone: "review",
    }
  }
  return {
    action: "Keep monitoring drift",
    body: `${summary.repos} repos passed validation with ${formatPercent(summary.citationCoverage)} citation coverage.`,
    label: "Run verdict",
    status: "Approved",
    tone: "approved",
  }
}

function artifactInsight(
  artifact: string,
  finding: QueueFinding | null,
  preview: ArtifactPreview | undefined,
) {
  if (artifact.startsWith("http")) {
    return {
      heading: "Source repository",
      body: finding
        ? `${finding.repo} source reference. Use this to inspect the upstream repo context behind the validation row.`
        : "External source reference for this validation row.",
      facts: ["External URL", "Not embedded in local snapshot"],
    }
  }

  if (!preview) {
    return {
      heading: "Artifact not embedded",
      body: "This artifact path exists on the row, but no preview was generated into the local dashboard snapshot.",
      facts: ["No local preview", "Regenerate snapshot after producing artifact"],
    }
  }

  if (preview.path.endsWith("live-repo-validation-results.json")) {
    return {
      heading: "Aggregate validation evidence",
      body: finding
        ? `${finding.repo} is backed by the live validation aggregate. It records permit status, expected rule checks, citation pass state, token use, and artifact paths.`
        : "Live validation aggregate with repo-level permit status, rule checks, citation pass state, and token use.",
      facts: [
        `${queueSummary.repos} repos validated`,
        `${queueSummary.findings} findings`,
        `${queueSummary.graphPaths} graph paths`,
        `${formatPercent(queueSummary.cacheHitRatio)} cache hit`,
      ],
    }
  }

  if (preview.path.endsWith("live-repo-validation-report.md")) {
    return {
      heading: "Reviewer summary report",
      body: "Human-readable validation report summarizing repo outcomes, findings, controls, citation checks, and cached-token savings.",
      facts: [
        `${queueSummary.passedRepos}/${queueSummary.repos} repos passed expectations`,
        `${formatPercent(queueSummary.citationCoverage)} citation coverage`,
        `${formatCompact(queueSummary.cachedTokens)} cached tokens`,
      ],
    }
  }

  return {
    heading: "Local artifact preview",
    body: "Repo-local artifact captured in the dashboard snapshot.",
    facts: [preview.kind, formatBytes(preview.sizeBytes)],
  }
}

function StatusBadge({ status }: { status: PermitStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn("apo-status-badge", `is-${status}`)}
    >
      {status === "approved" ? (
        <CheckCircleIcon data-icon="inline-start" weight="fill" />
      ) : status === "blocked" ? (
        <XCircleIcon data-icon="inline-start" weight="fill" />
      ) : (
        <WarningDiamondIcon data-icon="inline-start" weight="fill" />
      )}
      {statusLabels[status]}
    </Badge>
  )
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge
      variant="outline"
      className={cn("apo-severity-badge", `is-${severity}`)}
    >
      {severityLabels[severity]}
    </Badge>
  )
}

function TraceBadge({ state }: { state: TraceState }) {
  return (
    <Badge variant="outline" className={cn("apo-trace-badge", `is-${state}`)}>
      {state === "passed" ? (
        <CheckCircleIcon data-icon="inline-start" weight="fill" />
      ) : state === "blocked" ? (
        <XCircleIcon data-icon="inline-start" weight="fill" />
      ) : (
        <WarningDiamondIcon data-icon="inline-start" weight="fill" />
      )}
      {traceLabels[state]}
    </Badge>
  )
}

type DecisionLogTone = PermitStatus | "agent"

type DecisionLogEntry = {
  action: string
  actor: string
  detail: string
  ref: string
  tone: DecisionLogTone
}

function decisionLogEntries(finding: QueueFinding): DecisionLogEntry[] {
  const permitAction =
    finding.status === "approved"
      ? "Permit approved"
      : finding.status === "blocked"
        ? "Permit blocked"
        : "Needs review"
  const nextAction =
    finding.status === "approved"
      ? "Keep permit evidence attached"
      : finding.status === "blocked"
        ? "Request code or policy change"
        : "Route to owner for approval"

  return [
    {
      action: `Matched ${finding.rule}`,
      actor: "Scanner",
      detail: `${severityLabels[finding.severity]} severity. ${finding.evidence}`,
      ref: evidenceLocation(finding),
      tone: finding.status,
    },
    {
      action: "Mapped graph risk",
      actor: "Capability graph",
      detail: `${finding.capability}. ${finding.metrics.graphPaths} paths and ${finding.metrics.controls} controls evaluated.`,
      ref: `${finding.metrics.graphPaths} paths`,
      tone: finding.status,
    },
    {
      action: permitAction,
      actor: "Permit",
      detail: `${finding.confidence}% confidence from deterministic signals and policy checks.`,
      ref: statusLabels[finding.status],
      tone: finding.status,
    },
    {
      action: "Verified evidence",
      actor: "Deep Agent",
      detail: `${finding.metrics.citationCheckPassed ? "Citation passed" : "Citation needs review"}. ${finding.metrics.modelCalls} model calls, ${formatCompact(finding.metrics.cachedTokens)} cached tokens.`,
      ref: finding.artifacts[0] ? artifactLabel(finding.artifacts[0]) : finding.scanner,
      tone: "agent",
    },
    {
      action: nextAction,
      actor: "Next action",
      detail: finding.remediation,
      ref: finding.owner,
      tone: finding.status,
    },
  ]
}

function PermitGraphMark() {
  return (
    <svg
      aria-hidden="true"
      className="apo-brand-logo"
      fill="none"
      viewBox="0 0 28 28"
    >
      <path
        d="M9 5.75H19C20.24 5.75 21.25 6.76 21.25 8V20C21.25 21.24 20.24 22.25 19 22.25H9C7.76 22.25 6.75 21.24 6.75 20V8C6.75 6.76 7.76 5.75 9 5.75Z"
        opacity="0.38"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M14 6.75V21.25"
        opacity="0.42"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <path
        d="M8.8 18.2H11.3C12.74 18.2 13.9 17.04 13.9 15.6V12.4C13.9 10.96 15.06 9.8 16.5 9.8H19.2"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <circle cx="8.8" cy="18.2" r="2.2" fill="currentColor" />
      <circle cx="19.2" cy="9.8" r="2.2" fill="currentColor" />
    </svg>
  )
}

function DecisionLog({ finding }: { finding: QueueFinding }) {
  const entries = decisionLogEntries(finding)

  return (
    <section className="apo-decision-log" aria-label="Decision log">
      <div className="apo-decision-log-heading">
        <div className="apo-section-heading">
          <FlowArrowIcon />
          Decision Log
        </div>
        <span>{entries.length} steps</span>
      </div>
      <ol className="apo-decision-log-list">
        {entries.map((entry) => (
          <li key={`${entry.actor}-${entry.action}`}>
            <span className={cn("apo-log-dot", `is-${entry.tone}`)} />
            <div className="apo-log-main">
              <div className="apo-log-line">
                <strong>{entry.actor}</strong>
                <span>{entry.action}</span>
              </div>
              <p>{entry.detail}</p>
            </div>
            <code>{entry.ref}</code>
          </li>
        ))}
      </ol>
    </section>
  )
}

function AppSidebar({ summary }: { summary: QueueSummary }) {
  const verdict = verdictCopy(summary)

  return (
    <aside className="apo-sidebar" aria-label="Dashboard navigation">
      <div className="apo-brand">
        <div className="apo-brand-mark">
          <PermitGraphMark />
        </div>
        <div>
          <div className="apo-brand-title">PermitGraph</div>
          <div className="apo-brand-subtitle">Agent risk gate</div>
        </div>
      </div>

      <div className="apo-sidebar-panel" aria-label="Current scope decision">
        <div className="apo-sidebar-kicker">Current scope</div>
        <div className="apo-sidebar-decision">
          <span className={cn("apo-sidebar-decision-icon", `is-${verdict.tone}`)}>
            {verdict.tone === "blocked" ? (
              <XCircleIcon weight="fill" />
            ) : verdict.tone === "review" ? (
              <WarningDiamondIcon weight="fill" />
            ) : (
              <CheckCircleIcon weight="fill" />
            )}
          </span>
          <div>
            <div className="apo-sidebar-title">{verdict.status}</div>
            <p>{verdict.action}</p>
          </div>
        </div>
        <div className="apo-sidebar-stats">
          <span>{summary.repos} repos</span>
          <span>{summary.findings} findings</span>
          <span>{summary.graphPaths} paths</span>
        </div>
      </div>

      <div className="apo-sidebar-workflow" aria-label="Review workflow">
        <div className="apo-sidebar-kicker">Review flow</div>
        <ol>
          <li>
            <span>1</span>
            <div>
              <strong>Find risky rows</strong>
              <p>Start with blocked and high severity findings.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>Inspect evidence</strong>
              <p>Check scanner evidence, trace, policy, and artifacts.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>Decide permit</strong>
              <p>Request changes or approve a documented exception.</p>
            </div>
          </li>
        </ol>
      </div>
    </aside>
  )
}

function ThemeToggle({
  theme,
  onChange,
}: {
  theme: "light" | "dark"
  onChange: () => void
}) {
  return (
    <Button
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="apo-theme-toggle"
      data-testid="theme-toggle"
      onClick={onChange}
      size="icon-sm"
      variant="outline"
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </Button>
  )
}

function DashboardHeader({
  theme,
  onThemeChange,
}: {
  theme: "light" | "dark"
  onThemeChange: () => void
}) {
  return (
    <header className="apo-header">
      <div className="apo-header-title">
        <h1>{runMeta.title}</h1>
        <div className="apo-header-meta">
          <span>{runMeta.repo}</span>
          <span>{runMeta.branch}</span>
          <span>{runMeta.runId}</span>
        </div>
      </div>

      <div className="apo-header-actions">
        <ThemeToggle onChange={onThemeChange} theme={theme} />
        <Button variant="outline">
          <ArchiveBoxIcon data-icon="inline-start" />
          Artifacts
        </Button>
        <Button>
          <DownloadSimpleIcon data-icon="inline-start" />
          Export
        </Button>
      </div>
    </header>
  )
}

function SavedViews({
  activeView,
  onChange,
}: {
  activeView: string
  onChange: (view: string) => void
}) {
  return (
    <div className="apo-saved-views" aria-label="Saved views">
      {savedViews.map((view) => (
        <button
          className={cn("apo-saved-view", activeView === view.id && "is-active")}
          data-testid={`saved-view-${view.id}`}
          key={view.id}
          onClick={() => onChange(view.id)}
          type="button"
        >
          <span>{view.label}</span>
          <span>{view.count}</span>
        </button>
      ))}
    </div>
  )
}

function FilterBar({
  search,
  severity,
  onSearchChange,
  onSeverityChange,
}: {
  search: string
  severity: string
  onSearchChange: (value: string) => void
  onSeverityChange: (value: string) => void
}) {
  return (
    <section className="apo-filter-bar" aria-label="Queue filters">
      <div className="apo-search-control">
        <MagnifyingGlassIcon />
        <Input
          aria-label="Search findings"
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search rule, file, capability"
          value={search}
        />
      </div>

      <Select onValueChange={onSeverityChange} value={severity}>
        <SelectTrigger className="apo-select-trigger">
          <SelectValue placeholder="Severity" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="all">All severity</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </section>
  )
}

function RunScopeSelector({
  selectedRun,
  onRunChange,
}: {
  selectedRun: RunSnapshot
  onRunChange: (runId: string) => void
}) {
  const detail = runDetails[selectedRun.id]
  const selectedRepoId = detail?.repoId ?? selectedRun.repoId
  const selectedRepo = selectedRepoId === "all" ? null : (repoById(selectedRepoId) ?? null)
  const availableRuns = runOptionsForRepo(selectedRepo)
  const rowCount = detail?.rowIds.length ?? queueFindings.length
  const artifactAvailability = detail?.artifactAvailability ?? selectedRun.artifactStatus ?? "missing"
  const missingCount = detail?.missingArtifacts.length ?? 0

  return (
    <section className="apo-scope-bar" aria-label="Review scope">
      <div className="apo-scope-copy">
        <div className="apo-detail-kicker">Review scope</div>
        <h2>{selectedRepo ? selectedRepo.label : "All repositories"}</h2>
        <p>
          {rowCount} validation {rowCount === 1 ? "row" : "rows"} from{" "}
          {selectedRun.scope === "validation" ? "the full validation run" : selectedRun.label}.
        </p>
      </div>

      <div className="apo-scope-controls">
        <label className="apo-scope-field">
          <span>Repository</span>
          <Select
            onValueChange={(repoId) => {
              if (repoId === "all") {
                onRunChange(defaultSelectedRunId)
                return
              }

              const repo = repoById(repoId)
              if (repo) {
                onRunChange(repo.latestRunId)
              }
            }}
            value={selectedRepoId}
          >
            <SelectTrigger
              aria-label="Repository"
              className="apo-scope-select"
              data-testid="repo-scope-select"
              size="sm"
            >
              <SelectValue placeholder="Repository" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All repositories</SelectItem>
                {repos.map((repo) => (
                  <SelectItem key={repo.id} value={repo.id}>
                    {repo.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </label>

        <label className="apo-scope-field">
          <span>Run</span>
          <Select onValueChange={onRunChange} value={selectedRun.id}>
            <SelectTrigger
              aria-label="Run"
              className="apo-scope-select"
              data-testid="run-scope-select"
              size="sm"
            >
              <SelectValue placeholder="Run" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {availableRuns.map((run) => (
                  <SelectItem key={run.id} value={run.id}>
                    {run.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </label>
      </div>

      <div className="apo-scope-state">
        <StatusBadge status={selectedRun.status} />
        <Badge className={cn("apo-artifact-state", `is-${artifactAvailability}`)} variant="outline">
          {artifactAvailabilityLabel(artifactAvailability)}
          {missingCount > 0 ? ` (${missingCount})` : ""}
        </Badge>
      </div>
    </section>
  )
}

function RunStatusStrip({ summary }: { summary: QueueSummary }) {
  const verdict = verdictCopy(summary)
  const Icon =
    verdict.tone === "blocked"
      ? XCircleIcon
      : verdict.tone === "review"
        ? WarningDiamondIcon
        : CheckCircleIcon
  const metrics = [
    {
      label: "Findings",
      value: summary.findings.toString(),
      note: `${summary.repos} repos`,
    },
    {
      label: "Blocked",
      value: summary.blockedRepos.toString(),
      note: "must fix",
    },
    {
      label: "Citations",
      value: formatPercent(summary.citationCoverage),
      note: "grounded",
    },
    {
      label: "Cache",
      value: formatPercent(summary.cacheHitRatio),
      note: `${formatCompact(summary.cachedTokens)} saved`,
    },
  ]

  return (
    <section className={cn("apo-status-strip", `is-${verdict.tone}`)} aria-label="Run status">
      <div className="apo-status-verdict">
        <div className="apo-status-icon">
          <Icon weight="fill" />
        </div>
        <div>
          <div className="apo-status-label">{verdict.status}</div>
          <p>{verdict.action}</p>
        </div>
      </div>

      <div className="apo-status-divider" />

      <div className="apo-status-metrics" aria-label="Run metrics">
        {metrics.map((metric) => (
          <div className="apo-status-metric" key={metric.label}>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
            <em>{metric.note}</em>
          </div>
        ))}
      </div>
    </section>
  )
}

function FindingsTable({
  activeView,
  onSearchChange,
  rows,
  search,
  selectedId,
  severity,
  onSeverityChange,
  onSelect,
  onViewChange,
}: {
  activeView: string
  onSearchChange: (value: string) => void
  rows: QueueFinding[]
  search: string
  selectedId: string
  severity: string
  onSeverityChange: (value: string) => void
  onSelect: (id: string) => void
  onViewChange: (view: string) => void
}) {
  return (
    <Card className="apo-table-panel">
      <div className="apo-table-pinned">
        <div className="apo-table-heading-row">
          <div>
            <div className="apo-detail-kicker">Findings spreadsheet</div>
            <h2>Review queue</h2>
            <p>
              {rows.length} validation {rows.length === 1 ? "row" : "rows"}. Select a row to
              inspect evidence.
            </p>
          </div>
          <span className="apo-sort-label">Sorted by risk</span>
        </div>
        <div className="apo-table-controls">
          <SavedViews activeView={activeView} onChange={onViewChange} />
          <FilterBar
            onSearchChange={onSearchChange}
            onSeverityChange={onSeverityChange}
            search={search}
            severity={severity}
          />
        </div>
      </div>
      <CardContent className="apo-table-content">
        <div className="apo-table-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Finding</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead>Evidence</TableHead>
                <TableHead>Capability</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Commit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length > 0 ? (
                rows.map((row) => (
                  <TableRow
                    className="apo-finding-row"
                    data-state={row.id === selectedId ? "selected" : undefined}
                    data-testid={`finding-row-${row.id}`}
                    key={row.id}
                    onClick={() => onSelect(row.id)}
                    tabIndex={0}
                  >
                    <TableCell className="apo-finding-main-cell">
                      <div className="apo-finding-title">{row.title}</div>
                      <div className="apo-finding-meta">
                        <span>{row.id}</span>
                        <span>{row.repo}</span>
                        <span className="apo-row-action">Inspect</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell>
                      <SeverityBadge severity={row.severity} />
                    </TableCell>
                    <TableCell className="apo-rule-cell">{row.rule}</TableCell>
                    <TableCell className="apo-path-cell">{evidenceLocation(row)}</TableCell>
                    <TableCell>{row.capability}</TableCell>
                    <TableCell>{row.owner}</TableCell>
                    <TableCell className="apo-age-cell">{row.age}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell className="apo-empty-row" colSpan={8}>
                    <ShieldCheckIcon weight="duotone" />
                    <div>
                      <h3>No findings match filters</h3>
                      <p>Widen severity or search filters to restore queue rows.</p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function DetailRail({
  finding,
  onArtifactOpen,
}: {
  finding: QueueFinding
  onArtifactOpen: (artifact: string) => void
}) {
  const relatedTraceSteps = agentTraceSteps.filter((step) =>
    finding.traceIds.includes(step.id),
  )

  return (
    <aside className="apo-detail-rail" aria-label="Selected finding detail">
      <div className="apo-detail-pinned">
        <div className="apo-detail-kicker">Selected finding evidence</div>
        <div className="apo-detail-title-row">
          <h2>{finding.id}</h2>
          <StatusBadge status={finding.status} />
        </div>
        <p>{finding.summary}</p>
        <div className="apo-selected-meta">
          <span>{finding.rule}</span>
          <span>{severityLabels[finding.severity]}</span>
          <span>{finding.owner}</span>
        </div>
        <div className="apo-decision-actions">
          <Button variant="outline" size="sm">
            Request changes
          </Button>
          <Button size="sm">Approve exception</Button>
        </div>
      </div>

      <DecisionLog finding={finding} />

      <Tabs defaultValue="evidence" className="apo-detail-tabs">
        <TabsList className="apo-detail-tab-list">
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="trace">Trace</TabsTrigger>
          <TabsTrigger value="policy">Policy</TabsTrigger>
        </TabsList>

        <ScrollArea className="apo-detail-scroll">
          <TabsContent value="evidence">
            <EvidenceTab finding={finding} onArtifactOpen={onArtifactOpen} />
          </TabsContent>
          <TabsContent value="trace">
            <TraceTab steps={relatedTraceSteps} />
          </TabsContent>
          <TabsContent value="policy">
            <PolicyTab />
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </aside>
  )
}

function EvidenceTab({
  finding,
  onArtifactOpen,
}: {
  finding: QueueFinding
  onArtifactOpen: (artifact: string) => void
}) {
  return (
    <div className="apo-detail-section-stack">
      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <FileSearchIcon />
          Scanner evidence
        </div>
        <p>{finding.evidence}</p>
        <div className="apo-evidence-fact-grid">
          <div>
            <span>Rule</span>
            <strong>{finding.rule}</strong>
          </div>
          <div>
            <span>Severity</span>
            <strong>{severityLabels[finding.severity]}</strong>
          </div>
          <div>
            <span>Graph paths</span>
            <strong>{finding.metrics.graphPaths}</strong>
          </div>
          <div>
            <span>Controls</span>
            <strong>{finding.metrics.controls}</strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>{finding.confidence}%</strong>
          </div>
          <div>
            <span>Artifacts</span>
            <strong>{artifactAvailabilityLabel(finding.artifactStatus)}</strong>
          </div>
        </div>
        <div className="apo-code-line">
          <span>{finding.path}</span>
          <span>{finding.line > 0 ? `line ${finding.line}` : "artifact"}</span>
        </div>
      </section>

      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <FlowArrowIcon />
          Capability path
        </div>
        <div className="apo-path-chain">
          <span>repo file</span>
          <span>{finding.metrics.graphPaths} graph paths</span>
          <span>{finding.metrics.controls} controls</span>
          <span>{finding.capability}</span>
        </div>
      </section>

      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <ArchiveBoxIcon />
          Artifacts
        </div>
        <div className="apo-artifact-list">
          {finding.artifacts.map((artifact) => (
            <button
              className="apo-artifact-row"
              data-artifact={artifact}
              data-testid="artifact-row"
              key={artifact}
              onClick={() => onArtifactOpen(artifact)}
              type="button"
            >
              <DatabaseIcon />
              <span>{artifact}</span>
              <ArrowSquareOutIcon />
            </button>
          ))}
        </div>
        {finding.missingArtifacts.length > 0 ? (
          <div className="apo-missing-artifacts">
            Missing local proof: {finding.missingArtifacts.join(", ")}
          </div>
        ) : null}
      </section>

      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <ShieldCheckIcon />
          Remediation
        </div>
        <p>{finding.remediation}</p>
      </section>
    </div>
  )
}

function TraceTab({ steps }: { steps: AgentTraceStep[] }) {
  return (
    <div className="apo-detail-section-stack">
      {steps.map((step) => (
        <section className="apo-trace-step" key={step.id}>
          <div className="apo-trace-step-header">
            <div>
              <div className="apo-trace-title">{step.label}</div>
              <div className="apo-trace-meta">
                {step.tool} / {step.duration}
              </div>
            </div>
            <TraceBadge state={step.state} />
          </div>
          <p>{step.output}</p>
        </section>
      ))}
    </div>
  )
}

function PolicyTab() {
  return (
    <div className="apo-detail-section-stack">
      {policyControls.map((control) => (
        <section className="apo-policy-control" key={control.id}>
          <div>
            <div className="apo-policy-title">
              <LockKeyIcon />
              {control.label}
            </div>
            <p>{control.note}</p>
          </div>
          <TraceBadge state={control.state} />
        </section>
      ))}
    </div>
  )
}

function ArtifactDrawer({
  artifact,
  finding,
  preview,
  onOpenChange,
}: {
  artifact: string | null
  finding: QueueFinding | null
  preview: ArtifactPreview | undefined
  onOpenChange: (open: boolean) => void
}) {
  const isExternal = artifact?.startsWith("http") ?? false
  const insight = artifact ? artifactInsight(artifact, finding, preview) : null

  return (
    <Sheet open={artifact !== null} onOpenChange={onOpenChange}>
      <SheetContent className="apo-artifact-drawer">
        <SheetHeader className="apo-artifact-drawer-header">
          <div className="apo-detail-kicker">Artifact preview</div>
          <SheetTitle>{artifact ? artifactLabel(artifact) : "Artifact"}</SheetTitle>
          <SheetDescription>
            {preview
              ? "Artifact interpreted first, raw preview below."
              : "External artifact reference from the validation row."}
          </SheetDescription>
        </SheetHeader>

        {artifact ? (
          <div className="apo-artifact-drawer-body">
            {insight ? (
              <section className="apo-artifact-insight">
                <div className="apo-section-heading">
                  <RobotIcon />
                  {insight.heading}
                </div>
                <p>{insight.body}</p>
                <div className="apo-artifact-insight-facts">
                  {insight.facts.map((fact) => (
                    <span key={fact}>{fact}</span>
                  ))}
                </div>
              </section>
            ) : null}

            <div className="apo-artifact-meta-grid">
              <div>
                <span>Path</span>
                <strong>{artifact}</strong>
              </div>
              <div>
                <span>Kind</span>
                <strong>{preview?.kind ?? (isExternal ? "url" : "unknown")}</strong>
              </div>
              <div>
                <span>Size</span>
                <strong>{preview ? formatBytes(preview.sizeBytes) : "not local"}</strong>
              </div>
            </div>

            {preview ? (
              <ScrollArea className="apo-artifact-preview-scroll">
                <pre className="apo-artifact-preview">{preview.content}</pre>
                {preview.truncated ? (
                  <p className="apo-artifact-preview-note">Preview truncated at 12 KB.</p>
                ) : null}
              </ScrollArea>
            ) : (
              <div className="apo-artifact-empty-preview">
                <DatabaseIcon />
                <div>
                  <h3>No local preview</h3>
                  <p>
                    {isExternal
                      ? "This row points to the source repository."
                      : "This artifact was not generated into the dashboard snapshot."}
                  </p>
                  {isExternal ? (
                    <a href={artifact} rel="noreferrer" target="_blank">
                      Open source
                    </a>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

export function PermitReviewQueue() {
  const [activeView, setActiveView] = useState(savedViews[0]?.id ?? "all")
  const [selectedId, setSelectedId] = useState(queueFindings[0].id)
  const [selectedRun, setSelectedRun] = useState(defaultSelectedRunId)
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [severity, setSeverity] = useState("all")
  const [theme, setTheme] = useState<"light" | "dark">("light")

  const selectedRunRecord = runById(selectedRun) ?? runById(defaultSelectedRunId) ?? runs[0]
  const selectedRunDetail = selectedRunRecord ? runDetails[selectedRunRecord.id] : undefined
  const scopeRows = useMemo(() => rowsForRun(selectedRunDetail), [selectedRunDetail])
  const scopedSummary = useMemo(() => summaryForRun(selectedRunRecord), [selectedRunRecord])

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return scopeRows.filter((row) => {
      const matchesView = activeView === "all" || row.status === activeView
      const matchesSeverity = severity === "all" || row.severity === severity
      const matchesSearch =
        normalizedSearch.length === 0 ||
        [row.title, row.rule, row.path, row.capability, row.owner, row.repo, row.source]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch)

      return matchesView && matchesSeverity && matchesSearch
    })
  }, [activeView, scopeRows, search, severity])

  const selectedFinding =
    filteredRows.find((row) => row.id === selectedId) ??
    filteredRows[0] ??
    scopeRows[0] ??
    queueFindings[0]

  function handleRunChange(runId: string) {
    const nextDetail = runDetails[runId]
    setSelectedRun(runId)

    const nextRow = rowsForRun(nextDetail)[0]
    if (nextRow) {
      setSelectedId(nextRow.id)
    }
  }

  return (
    <div className={cn("apo-dashboard", theme === "dark" && "dark")}>
      <AppSidebar summary={scopedSummary} />
      <main className="apo-main">
        <DashboardHeader
          onThemeChange={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
          theme={theme}
        />
        <div className="apo-workspace">
          <section className="apo-dashboard-stack" aria-label="Agent risk review">
            {selectedRunRecord ? (
              <RunScopeSelector selectedRun={selectedRunRecord} onRunChange={handleRunChange} />
            ) : null}
            <RunStatusStrip summary={scopedSummary} />

            <FindingsTable
              activeView={activeView}
              onSearchChange={setSearch}
              onSeverityChange={setSeverity}
              onSelect={setSelectedId}
              onViewChange={setActiveView}
              rows={filteredRows}
              search={search}
              selectedId={selectedFinding.id}
              severity={severity}
            />
            {filteredRows.length > 0 ? (
              <DetailRail finding={selectedFinding} onArtifactOpen={setSelectedArtifact} />
            ) : null}
          </section>
        </div>
      </main>
      <ArtifactDrawer
        artifact={selectedArtifact}
        finding={selectedFinding}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null)
          }
        }}
        preview={selectedArtifact ? artifactPreviews[selectedArtifact] : undefined}
      />
      <Separator className="apo-mobile-separator" />
    </div>
  )
}
