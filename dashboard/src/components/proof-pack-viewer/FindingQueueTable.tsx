import {
  CheckCircleIcon,
  MagnifyingGlassIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react"
import { type FormEvent, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { ApiStatus, RunEvent, ScanJob } from "@/data/liveApi"
import type { QueueFinding } from "@/data/permitQueue"
import { cn } from "@/lib/utils"
import { StatusBadge } from "./StatusBadge"
import {
  displayFindingTitle,
  policyCheckDescription,
  policyCheckLabel,
} from "./proofPackUtils"

export function FindingQueueTable({
  apiStatus,
  error,
  findings,
  generatedAt,
  isQueueing,
  jobEvents,
  jobs,
  onQueueScan,
  onSearchChange,
  onSelectFinding,
  onCloseAddRepository,
  queueError,
  recentJob,
  search,
  selectedFindingId,
  showAddRepository,
}: {
  apiStatus: ApiStatus
  error: string | null
  findings: QueueFinding[]
  generatedAt: string | null
  isQueueing: boolean
  jobEvents: RunEvent[]
  jobs: ScanJob[]
  onCloseAddRepository: () => void
  onQueueScan: (input: {
    branch: string
    label: string
    localPath: string
  }) => Promise<void>
  onSearchChange: (value: string) => void
  onSelectFinding: (finding: QueueFinding) => void
  queueError: string | null
  recentJob: ScanJob | null
  search: string
  selectedFindingId: string
  showAddRepository: boolean
}) {
  const activeJobs = jobs.filter((job) =>
    ["queued", "running", "failed"].includes(job.status),
  )

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border px-6 py-5">
        <div className="grid gap-5">
          <label className="relative block min-w-0">
            <MagnifyingGlassIcon
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              size={16}
            />
            <Input
              aria-label="Search findings"
              className="h-10 rounded-lg border-border bg-background pl-9"
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search by finding, policy, or repository"
              value={search}
            />
          </label>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-6 py-6">
          <LiveStatusStrip
            apiStatus={apiStatus}
            error={error}
            generatedAt={generatedAt}
            jobs={activeJobs}
          />

          {showAddRepository ? (
            <AddRepositoryPanel
              isQueueing={isQueueing}
              onClose={onCloseAddRepository}
              onQueueScan={onQueueScan}
              queueError={queueError}
              recentJob={recentJob}
            />
          ) : null}

          {recentJob || jobEvents.length > 0 ? (
            <QueueProgressPanel events={jobEvents} job={recentJob} />
          ) : null}

          <div className="grid grid-cols-[minmax(360px,1fr)_136px_minmax(260px,0.75fr)_minmax(150px,0.45fr)_96px] items-center gap-4 border-b border-border py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground max-xl:grid-cols-[minmax(260px,1fr)_128px_minmax(240px,0.8fr)] max-xl:[&>div:nth-child(n+4)]:hidden max-sm:hidden">
            <div className="pl-4">Risk</div>
            <div>Status</div>
            <div>Policy check</div>
            <div>Repository</div>
            <div>Scan date</div>
          </div>

          <div>
            {findings.map((finding) => (
              <button
                className={cn(
                  "grid w-full grid-cols-[minmax(360px,1fr)_136px_minmax(260px,0.75fr)_minmax(150px,0.45fr)_96px] items-center gap-4 border-b border-border/80 py-4 text-left transition-colors hover:bg-muted/30 max-xl:grid-cols-[minmax(260px,1fr)_128px_minmax(240px,0.8fr)] max-sm:grid-cols-1 max-sm:gap-2",
                  selectedFindingId === finding.id && "bg-primary/5",
                )}
                data-finding-id={finding.id}
                key={finding.id}
                onClick={() => onSelectFinding(finding)}
                type="button"
              >
                <div className="min-w-0 pl-4">
                  <div className="line-clamp-2 text-sm font-semibold leading-5">
                    {displayFindingTitle(finding)}
                  </div>
                </div>
                <StatusBadge status={finding.status} />
                <PolicyCheck finding={finding} />
                <span className="break-words text-sm text-muted-foreground max-xl:hidden">
                  {finding.repo}
                </span>
                <span className="whitespace-nowrap text-sm text-muted-foreground max-xl:hidden">
                  {finding.age}
                </span>
              </button>
            ))}

            {findings.length === 0 ? (
              <div className="border-b border-border/80 py-16 text-center text-sm text-muted-foreground">
                No repositories match this search or status filter.
              </div>
            ) : null}
          </div>
        </div>
      </ScrollArea>
    </section>
  )
}

function PolicyCheck({ finding }: { finding: QueueFinding }) {
  const label = policyCheckLabel(finding)
  const description = policyCheckDescription(finding)

  return (
    <span className="grid min-w-0 gap-1 text-sm leading-5" title={description}>
      <span className="font-medium text-foreground">{label}</span>
      <span className="text-xs leading-5 text-muted-foreground">
        {description}
      </span>
    </span>
  )
}

function LiveStatusStrip({
  apiStatus,
  error,
  generatedAt,
  jobs,
}: {
  apiStatus: ApiStatus
  error: string | null
  generatedAt: string | null
  jobs: ScanJob[]
}) {
  const isLive = apiStatus === "live"

  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4 text-sm text-muted-foreground">
      <div className="flex min-w-0 items-center gap-2">
        {isLive ? (
          <CheckCircleIcon className="text-apo-approved" size={16} weight="fill" />
        ) : (
          <WarningCircleIcon className="text-apo-review" size={16} weight="fill" />
        )}
        <span className="font-medium text-foreground">
          {isLive ? "Live Worker data" : "Static snapshot fallback"}
        </span>
        <span className="truncate">
          {isLive
            ? `Last read ${formatTimestamp(generatedAt)}`
            : error || "Start the Worker API to queue and refresh scans."}
        </span>
      </div>
      {jobs.length > 0 ? (
        <span className="shrink-0 font-mono text-xs">
          {jobs.length} open job{jobs.length === 1 ? "" : "s"}
        </span>
      ) : null}
    </div>
  )
}

function AddRepositoryPanel({
  isQueueing,
  onClose,
  onQueueScan,
  queueError,
  recentJob,
}: {
  isQueueing: boolean
  onClose: () => void
  onQueueScan: (input: {
    branch: string
    label: string
    localPath: string
  }) => Promise<void>
  queueError: string | null
  recentJob: ScanJob | null
}) {
  const [localPath, setLocalPath] = useState("")
  const [label, setLabel] = useState("")
  const [branch, setBranch] = useState("main")

  async function queueRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedPath = localPath.trim()
    if (!trimmedPath) return
    await onQueueScan({
      branch,
      label,
      localPath: trimmedPath,
    })
  }

  return (
    <div className="mb-5 rounded-lg border border-border bg-background p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Queue a repository scan</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Add an absolute local repository path. The local runner claims it from Postgres.
          </p>
        </div>
        <Button onClick={onClose} size="sm" variant="ghost">
          Close
        </Button>
      </div>

      <form
        className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(180px,0.35fr)_140px_auto]"
        onSubmit={queueRepository}
      >
        <Input
          aria-label="Local repository path"
          onChange={(event) => setLocalPath(event.target.value)}
          placeholder="/absolute/path/to/repository"
          value={localPath}
        />
        <Input
          aria-label="Repository label"
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Repository label"
          value={label}
        />
        <Input
          aria-label="Default branch"
          onChange={(event) => setBranch(event.target.value)}
          placeholder="main"
          value={branch}
        />
        <Button disabled={localPath.trim().length === 0 || isQueueing} type="submit">
          {isQueueing ? "Queueing" : "Queue scan"}
        </Button>
      </form>

      {queueError ? (
        <div className="mt-3 rounded-md border border-apo-blocked-border bg-apo-blocked-soft px-3 py-2 text-sm text-apo-blocked">
          {queueError}
        </div>
      ) : null}

      {recentJob ? (
        <div className="mt-3 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          Queued {recentJob.repositoryLabel}. Run{" "}
          <code className="font-mono text-xs text-foreground">agent-permit runner --once</code>{" "}
          to process it locally.
        </div>
      ) : null}
    </div>
  )
}

function QueueProgressPanel({
  events,
  job,
}: {
  events: RunEvent[]
  job: ScanJob | null
}) {
  return (
    <div className="mb-5 rounded-lg border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Latest queued scan</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {job
              ? `${job.repositoryLabel} is ${job.status}.`
              : "Waiting for runner events."}
          </p>
        </div>
        {job ? (
          <span className="rounded-full border border-border px-2 py-1 font-mono text-xs text-muted-foreground">
            {job.id}
          </span>
        ) : null}
      </div>

      {events.length > 0 ? (
        <div className="mt-4 grid gap-2">
          {events.slice(-5).map((event) => (
            <div
              className="grid grid-cols-[120px_minmax(0,1fr)] gap-3 text-sm"
              key={event.id}
            >
              <span className="font-mono text-xs text-muted-foreground">
                {event.eventName}
              </span>
              <span className="truncate text-muted-foreground">
                {eventSummary(event)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 text-sm text-muted-foreground">
          No runner events yet.
        </div>
      )}
    </div>
  )
}

function eventSummary(event: RunEvent) {
  const status = event.payload.status
  const findings = event.payload.findings
  if (typeof status === "string") return status
  if (typeof findings === "number") return `${findings} findings`
  return formatTimestamp(event.occurredAt)
}

function formatTimestamp(value: string | null) {
  if (!value) return "not yet"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  })
}
