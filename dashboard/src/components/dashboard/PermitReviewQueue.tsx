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
  PulseIcon,
  RobotIcon,
  ShieldCheckIcon,
  WarningDiamondIcon,
  XCircleIcon,
} from "@phosphor-icons/react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
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
  policyControls,
  queueFindings,
  savedViews,
  type AgentTraceStep,
  type PermitStatus,
  type QueueFinding,
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

function AppSidebar() {
  return (
    <aside className="apo-sidebar" aria-label="Dashboard navigation">
      <div className="apo-brand">
        <div className="apo-brand-mark">
          <ShieldCheckIcon weight="fill" />
        </div>
        <div>
          <div className="apo-brand-title">Agent Permit</div>
          <div className="apo-brand-subtitle">Office</div>
        </div>
      </div>

      <div className="apo-sidebar-panel" aria-label="Current dashboard context">
        <div className="apo-sidebar-kicker">Current surface</div>
        <div className="apo-sidebar-title">
          <FileSearchIcon weight="fill" />
          <span>Findings queue</span>
        </div>
        <p>Review scanner findings, agent evidence, and permit decisions for one run.</p>
        <div className="apo-sidebar-stats">
          <span>36 findings</span>
          <span>14 trace steps</span>
        </div>
      </div>
    </aside>
  )
}

function DashboardHeader() {
  return (
    <header className="apo-header">
      <div className="apo-header-title">
        <h1>Permit Review Queue</h1>
        <div className="apo-header-meta">
          <span>t3-oss/create-t3-app</span>
          <span>main</span>
          <span>run_2026_06_11_1842</span>
        </div>
      </div>

      <div className="apo-header-actions">
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

function SectionIntro({
  description,
  label,
  title,
}: {
  description: string
  label: string
  title: string
}) {
  return (
    <div className="apo-section-intro">
      <div className="apo-section-label">{label}</div>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
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

function SummaryTiles({ rows }: { rows: QueueFinding[] }) {
  const blocked = rows.filter((row) => row.status === "blocked").length
  const review = rows.filter((row) => row.status === "needs-review").length
  const cited = 98
  const evals = 4

  return (
    <div className="apo-summary-grid" aria-label="Queue summary">
      <MetricTile
        icon={WarningDiamondIcon}
        label="Needs review"
        note="Manual decision"
        tone="review"
        value={review.toString()}
      />
      <MetricTile
        icon={XCircleIcon}
        label="Blocked permits"
        note="Must fix first"
        tone="blocked"
        value={blocked.toString()}
      />
      <MetricTile
        icon={RobotIcon}
        label="Citation coverage"
        note="Deep Agent grounded"
        tone="agent"
        value={`${cited}%`}
      />
      <MetricTile
        icon={PulseIcon}
        label="Eval drifts"
        note="Model quality watch"
        tone="artifact"
        value={evals.toString()}
      />
    </div>
  )
}

function MetricTile({
  icon: Icon,
  label,
  note,
  tone,
  value,
}: {
  icon: typeof WarningDiamondIcon
  label: string
  note: string
  tone: string
  value: string
}) {
  return (
    <div className={cn("apo-metric-tile", `is-${tone}`)}>
      <div className="apo-metric-icon">
        <Icon weight="duotone" />
      </div>
      <div>
        <div className="apo-metric-value">{value}</div>
        <div className="apo-metric-label">{label}</div>
        <div className="apo-metric-note">{note}</div>
      </div>
    </div>
  )
}

function FindingsTable({
  rows,
  selectedId,
  onSelect,
}: {
  rows: QueueFinding[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <Card className="apo-table-panel">
      <div className="apo-table-pinned">
        <div className="apo-detail-kicker">Findings spreadsheet</div>
        <div className="apo-detail-title-row">
          <h2>Review queue</h2>
          <span className="apo-sort-label">Sorted by risk</span>
        </div>
        <p>
          {rows.length} deterministic scanner findings. Select a row to inspect evidence.
        </p>
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
                <TableHead>Age</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  className="apo-finding-row"
                  data-state={row.id === selectedId ? "selected" : undefined}
                  key={row.id}
                  onClick={() => onSelect(row.id)}
                  tabIndex={0}
                >
                  <TableCell className="apo-finding-main-cell">
                    <div className="apo-finding-title">{row.title}</div>
                    <div className="apo-finding-meta">
                      <span>{row.id}</span>
                      <span>{row.repo}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                  <TableCell>
                    <SeverityBadge severity={row.severity} />
                  </TableCell>
                  <TableCell className="apo-rule-cell">{row.rule}</TableCell>
                  <TableCell className="apo-path-cell">
                    {row.path}:{row.line}
                  </TableCell>
                  <TableCell>{row.capability}</TableCell>
                  <TableCell>{row.owner}</TableCell>
                  <TableCell className="apo-age-cell">{row.age}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function DetailRail({ finding }: { finding: QueueFinding }) {
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
        <div className="apo-decision-actions">
          <Button variant="outline" size="sm">
            Request changes
          </Button>
          <Button size="sm">Approve exception</Button>
        </div>
      </div>

      <Tabs defaultValue="evidence" className="apo-detail-tabs">
        <TabsList className="apo-detail-tab-list">
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="trace">Trace</TabsTrigger>
          <TabsTrigger value="policy">Policy</TabsTrigger>
        </TabsList>

        <ScrollArea className="apo-detail-scroll">
          <TabsContent value="evidence">
            <EvidenceTab finding={finding} />
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

function EvidenceTab({ finding }: { finding: QueueFinding }) {
  return (
    <div className="apo-detail-section-stack">
      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <FileSearchIcon />
          Scanner evidence
        </div>
        <p>{finding.evidence}</p>
        <div className="apo-code-line">
          <span>{finding.path}</span>
          <span>line {finding.line}</span>
        </div>
      </section>

      <section className="apo-detail-section">
        <div className="apo-section-heading">
          <FlowArrowIcon />
          Capability path
        </div>
        <div className="apo-path-chain">
          <span>repo file</span>
          <span>tool context</span>
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
            <button className="apo-artifact-row" key={artifact} type="button">
              <DatabaseIcon />
              <span>{artifact}</span>
              <ArrowSquareOutIcon />
            </button>
          ))}
        </div>
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

function EmptyState() {
  return (
    <Card className="apo-empty-panel">
      <CardContent className="apo-empty-content">
        <ShieldCheckIcon weight="duotone" />
        <div>
          <h2>No findings match filters</h2>
          <p>Widen severity or search filters to restore queue rows.</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function PermitReviewQueue() {
  const [activeView, setActiveView] = useState("needs-review")
  const [selectedId, setSelectedId] = useState(queueFindings[0].id)
  const [search, setSearch] = useState("")
  const [severity, setSeverity] = useState("all")

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return queueFindings.filter((row) => {
      const matchesSeverity = severity === "all" || row.severity === severity
      const matchesSearch =
        normalizedSearch.length === 0 ||
        [row.title, row.rule, row.path, row.capability, row.owner]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch)

      return matchesSeverity && matchesSearch
    })
  }, [search, severity])

  const selectedFinding =
    filteredRows.find((row) => row.id === selectedId) ?? filteredRows[0] ?? queueFindings[0]

  return (
    <div className="apo-dashboard">
      <AppSidebar />
      <main className="apo-main">
        <DashboardHeader />
        <div className="apo-workspace">
          <section className="apo-dashboard-stack" aria-label="Permit findings">
            <div className="apo-section-group">
              <SectionIntro
                description="These four widgets summarize the current scan before any filtering."
                label="Run overview"
                title="Decision snapshot"
              />
              <SummaryTiles rows={filteredRows} />
            </div>

            <div className="apo-section-group">
              <SectionIntro
                description="Saved views choose the work queue. Filters narrow the spreadsheet rows."
                label="Queue setup"
                title="Choose what to review"
              />
              <div className="apo-queue-controls">
                <SavedViews activeView={activeView} onChange={setActiveView} />
                <FilterBar
                  onSearchChange={setSearch}
                  onSeverityChange={setSeverity}
                  search={search}
                  severity={severity}
                />
              </div>
            </div>

            {filteredRows.length > 0 ? (
              <FindingsTable
                onSelect={setSelectedId}
                rows={filteredRows}
                selectedId={selectedFinding.id}
              />
            ) : (
              <EmptyState />
            )}
            <DetailRail finding={selectedFinding} />
          </section>
        </div>
      </main>
      <Separator className="apo-mobile-separator" />
    </div>
  )
}
