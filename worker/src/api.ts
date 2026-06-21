import type { Env, SqlClient, SqlRow, SqlValue } from "./db";
import { ApiError, createSqlClient } from "./db";

type JsonObject = Record<string, unknown>;

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const SSE_HEADERS = {
  "content-type": "text/event-stream; charset=utf-8",
  "cache-control": "no-store",
  connection: "keep-alive",
};

export async function handleRequest(
  request: Request,
  env: Env,
  sql?: SqlClient,
): Promise<Response> {
  const url = new URL(request.url);
  try {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    if (request.method === "GET" && url.pathname === "/api/health") {
      return json({ status: "ok" });
    }
    const db = sql ?? createSqlClient(env);
    if (request.method === "GET" && url.pathname === "/api/repos") {
      return json({ repositories: await listRepositories(db) });
    }
    if (request.method === "GET" && url.pathname === "/api/runs") {
      return json({ runs: await listRuns(db) });
    }
    if (request.method === "GET" && url.pathname === "/api/findings") {
      return json({ findings: await listFindings(db) });
    }
    if (request.method === "GET" && url.pathname === "/api/snapshot") {
      return json(await buildSnapshot(db));
    }
    if (request.method === "GET" && url.pathname === "/api/jobs") {
      return json({ jobs: await listJobs(db, url.searchParams.get("status")) });
    }
    if (request.method === "GET" && url.pathname === "/api/job") {
      return json({ job: await getJob(db, requiredSearchParam(url, "id")) });
    }
    if (request.method === "POST" && url.pathname === "/api/jobs") {
      return json(await createJob(request, db), { status: 201 });
    }
    if (request.method === "GET" && url.pathname === "/api/events") {
      return streamEvents(url, db);
    }
    return json({ error: "not_found" }, { status: 404 });
  } catch (error) {
    if (error instanceof ApiError) {
      return json({ error: error.message }, { status: error.status });
    }
    return json({ error: "internal_error" }, { status: 500 });
  }
}

async function listRepositories(sql: SqlClient): Promise<SqlRow[]> {
  return sql(
    `
    SELECT id, label, local_path, branch, updated_at
    FROM repositories
    ORDER BY updated_at DESC
    LIMIT 50
    `,
  );
}

async function listRuns(sql: SqlClient): Promise<SqlRow[]> {
  return sql(
    `
    SELECT scan_runs.id, scan_runs.job_id, scan_runs.repository_id,
           scan_runs.run_id, scan_runs.permit_status, scan_runs.status,
           scan_runs.findings_count, scan_runs.graph_paths_count,
           scan_runs.controls_count, scan_runs.completed_at,
           scan_runs.files_indexed, scan_runs.artifact_dir,
           repositories.label AS repository_label,
           repositories.local_path,
           repositories.branch
    FROM scan_runs
    JOIN repositories ON repositories.id = scan_runs.repository_id
    ORDER BY scan_runs.completed_at DESC NULLS LAST
    LIMIT 50
    `,
  );
}

async function listFindings(sql: SqlClient): Promise<SqlRow[]> {
  return sql(
    `
    SELECT findings.finding_id, findings.title, findings.rule_id,
           findings.severity, findings.status, findings.path,
           findings.line_start, findings.recommendation, findings.risk,
           repositories.id AS repository_id,
           repositories.label AS repository_label,
           repositories.local_path,
           repositories.branch,
           scan_runs.run_id,
           scan_runs.permit_status,
           scan_runs.findings_count,
           scan_runs.graph_paths_count,
           scan_runs.controls_count,
           scan_runs.artifact_dir
    FROM findings
    JOIN scan_runs ON scan_runs.id = findings.scan_run_id
    JOIN repositories ON repositories.id = scan_runs.repository_id
    ORDER BY scan_runs.completed_at DESC NULLS LAST, findings.severity ASC
    LIMIT 100
    `,
  );
}

async function listJobs(
  sql: SqlClient,
  status: string | null = null,
): Promise<SqlRow[]> {
  const params: SqlValue[] = [];
  const statusClause = status ? "WHERE scan_jobs.status = $1" : "";
  if (status) {
    params.push(status);
  }
  return sql(
    `
    SELECT scan_jobs.id, scan_jobs.repository_id, scan_jobs.mode,
           scan_jobs.status, scan_jobs.requested_at, scan_jobs.claimed_at,
           scan_jobs.completed_at, scan_jobs.error,
           repositories.label AS repository_label,
           repositories.local_path,
           repositories.branch
    FROM scan_jobs
    JOIN repositories ON repositories.id = scan_jobs.repository_id
    ${statusClause}
    ORDER BY scan_jobs.requested_at DESC
    LIMIT 50
    `,
    params,
  );
}

async function getJob(sql: SqlClient, jobId: string): Promise<SqlRow> {
  const rows = await sql(
    `
    SELECT scan_jobs.id, scan_jobs.repository_id, scan_jobs.mode,
           scan_jobs.status, scan_jobs.requested_at, scan_jobs.claimed_at,
           scan_jobs.completed_at, scan_jobs.error,
           repositories.label AS repository_label,
           repositories.local_path,
           repositories.branch
    FROM scan_jobs
    JOIN repositories ON repositories.id = scan_jobs.repository_id
    WHERE scan_jobs.id = $1
    LIMIT 1
    `,
    [jobId],
  );
  if (!rows[0]) {
    throw new ApiError(404, "job_not_found");
  }
  return rows[0];
}

async function buildSnapshot(sql: SqlClient): Promise<JsonObject> {
  const [repositories, runs, findings, jobs, queuedJobs] = await Promise.all([
    listRepositories(sql),
    listRuns(sql),
    listFindings(sql),
    listJobs(sql),
    countJobs(sql, "queued"),
  ]);
  return {
    generatedAt: new Date().toISOString(),
    counts: {
      repositories: repositories.length,
      runs: runs.length,
      findings: findings.length,
      queuedJobs,
    },
    repositories,
    runs,
    findings,
    jobs,
  };
}

async function countJobs(sql: SqlClient, status: string): Promise<number> {
  const rows = await sql(
    "SELECT COUNT(*)::int AS count FROM scan_jobs WHERE status = $1",
    [status],
  );
  return Number(rows[0]?.count ?? 0);
}

async function createJob(request: Request, sql: SqlClient): Promise<JsonObject> {
  const payload = await readJson(request);
  const localPath =
    optionalString(payload, "localPath") ?? optionalString(payload, "local_path");
  if (!localPath) {
    throw new ApiError(400, "localPath is required");
  }
  if (!localPath.startsWith("/")) {
    throw new ApiError(400, "localPath must be absolute");
  }
  const label =
    optionalString(payload, "label") ??
    optionalString(payload, "repo_label") ??
    pathLabel(localPath);
  const branch = optionalString(payload, "branch");
  const mode = optionalString(payload, "mode") ?? "scan";
  if (mode !== "scan") {
    throw new ApiError(400, "mode must be scan");
  }

  const repositoryId = await stableId("repo", localPath);
  const jobId = `job_${crypto.randomUUID()}`;
  await sql(
    `
    INSERT INTO repositories (id, label, local_path, branch)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (id) DO UPDATE SET
      label = EXCLUDED.label,
      local_path = EXCLUDED.local_path,
      branch = EXCLUDED.branch,
      updated_at = now()
    `,
    [repositoryId, label, localPath, branch],
  );
  await sql(
    `
    INSERT INTO scan_jobs (id, repository_id, mode, status)
    VALUES ($1, $2, $3, 'queued')
    `,
    [jobId, repositoryId, mode],
  );
  return {
    job: {
      id: jobId,
      repositoryId,
      status: "queued",
      mode,
    },
  };
}

async function streamEvents(url: URL, sql: SqlClient): Promise<Response> {
  const jobId = url.searchParams.get("jobId");
  if (!jobId) {
    throw new ApiError(400, "jobId is required");
  }
  const after = Number(url.searchParams.get("after") ?? "0");
  const rows = await sql(
    `
    SELECT id, event_name, sequence, occurred_at, payload_json
    FROM run_events
    WHERE job_id = $1 AND id > $2
    ORDER BY id ASC
    LIMIT 100
    `,
    [jobId, after],
  );
  const body = rows.map(formatSseEvent).join("");
  return new Response(body, { headers: withCors(SSE_HEADERS) });
}

function formatSseEvent(row: SqlRow): string {
  return [
    `id: ${String(row.id)}`,
    `event: ${String(row.event_name)}`,
    `data: ${JSON.stringify(row)}`,
    "",
    "",
  ].join("\n");
}

async function readJson(request: Request): Promise<JsonObject> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    throw new ApiError(400, "request body must be JSON");
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ApiError(400, "request body must be a JSON object");
  }
  return payload as JsonObject;
}

function requiredString(payload: JsonObject, key: string): string {
  const value = payload[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new ApiError(400, `${key} is required`);
  }
  return value;
}

function requiredSearchParam(url: URL, key: string): string {
  const value = url.searchParams.get(key);
  if (!value) {
    throw new ApiError(400, `${key} is required`);
  }
  return value;
}

function optionalString(payload: JsonObject, key: string): string | null {
  const value = payload[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    throw new ApiError(400, `${key} must be a string`);
  }
  return value.trim() || null;
}

function pathLabel(localPath: string): string {
  const parts = localPath.split("/").filter(Boolean);
  return parts.at(-1) ?? localPath;
}

async function stableId(prefix: string, value: string): Promise<string> {
  const bytes = new TextEncoder().encode(`${prefix}\0${value}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return hex.slice(0, 32);
}

function json(
  payload: JsonObject,
  init: ResponseInit = {},
): Response {
  return new Response(JSON.stringify(payload), {
    ...init,
    headers: withCors({ ...JSON_HEADERS, ...init.headers }),
  });
}

function corsHeaders(): Headers {
  return withCors({});
}

function withCors(headers: HeadersInit): Headers {
  const merged = new Headers(headers);
  merged.set("access-control-allow-origin", "*");
  merged.set("access-control-allow-methods", "GET,POST,OPTIONS");
  merged.set("access-control-allow-headers", "content-type");
  return merged;
}
