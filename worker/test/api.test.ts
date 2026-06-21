import { describe, expect, test } from "bun:test";
import { handleRequest } from "../src/api";
import type { SqlClient, SqlRow } from "../src/db";

type ApiPayload = Record<string, unknown>;

function request(path: string, init?: RequestInit): Request {
  return new Request(`http://localhost${path}`, init);
}

function sqlWithRows(rows: SqlRow[]): SqlClient {
  return async () => rows;
}

describe("worker api", () => {
  test("health does not require database", async () => {
    const response = await handleRequest(request("/api/health"), {});

    expect(response.status).toBe(200);
    const payload = (await response.json()) as ApiPayload;

    expect(payload).toEqual({ status: "ok" });
  });

  test("snapshot returns flat dashboard data", async () => {
    const calls: string[] = [];
    const sql: SqlClient = async (query) => {
      calls.push(query);
      if (query.includes("FROM repositories")) {
        return [{ id: "repo_1", label: "demo" }];
      }
      if (query.includes("FROM scan_runs")) {
        return [{ run_id: "run_1", permit_status: "approved" }];
      }
      if (query.includes("FROM findings")) {
        return [{ finding_id: "finding_1", title: "Review CI permissions" }];
      }
      if (query.includes("FROM scan_jobs") && !query.includes("COUNT")) {
        return [{ id: "job_1", status: "queued" }];
      }
      if (query.includes("COUNT")) {
        return [{ count: 2 }];
      }
      return [];
    };

    const response = await handleRequest(request("/api/snapshot"), {}, sql);
    const payload = (await response.json()) as {
      counts: {
        repositories: number;
        runs: number;
        findings: number;
        queuedJobs: number;
      };
      jobs: Array<{ id: string; status: string }>;
    };

    expect(response.status).toBe(200);
    expect(payload.counts).toEqual({
      repositories: 1,
      runs: 1,
      findings: 1,
      queuedJobs: 2,
    });
    expect(payload.jobs).toEqual([{ id: "job_1", status: "queued" }]);
    expect(calls).toHaveLength(5);
  });

  test("job creation validates and inserts queued job", async () => {
    const calls: Array<{ query: string; params: unknown[] }> = [];
    const sql: SqlClient = async (query, params) => {
      calls.push({ query, params: params ?? [] });
      return [];
    };
    const response = await handleRequest(
      request("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          localPath: "/tmp/demo",
          label: "demo",
          branch: "main",
        }),
      }),
      {},
      sql,
    );
    const payload = (await response.json()) as {
      job: {
        status: string;
        mode: string;
      };
    };

    expect(response.status).toBe(201);
    expect(payload.job.status).toBe("queued");
    expect(payload.job.mode).toBe("scan");
    expect(calls).toHaveLength(2);
    expect(calls[0]?.params?.[1]).toBe("demo");
    expect(calls[1]?.params?.[2]).toBe("scan");
  });

  test("job creation accepts snake case payload", async () => {
    const sql: SqlClient = async () => [];
    const response = await handleRequest(
      request("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          local_path: "/tmp/demo",
          repo_label: "demo",
        }),
      }),
      {},
      sql,
    );
    const payload = (await response.json()) as {
      job: {
        status: string;
      };
    };

    expect(response.status).toBe(201);
    expect(payload.job.status).toBe("queued");
  });

  test("jobs endpoint lists queued scans", async () => {
    const calls: Array<{ query: string; params: unknown[] }> = [];
    const sql: SqlClient = async (query, params) => {
      calls.push({ query, params: params ?? [] });
      return [{ id: "job_1", status: "queued" }];
    };
    const response = await handleRequest(
      request("/api/jobs?status=queued"),
      {},
      sql,
    );
    const payload = (await response.json()) as {
      jobs: Array<{ id: string; status: string }>;
    };

    expect(response.status).toBe(200);
    expect(payload.jobs[0]).toEqual({ id: "job_1", status: "queued" });
    expect(calls[0]?.params).toEqual(["queued"]);
  });

  test("events endpoint emits server-sent events", async () => {
    const response = await handleRequest(
      request("/api/events?jobId=job_1&after=10"),
      {},
      sqlWithRows([
        {
          id: 11,
          event_name: "scan_completed",
          sequence: 9,
          occurred_at: "2026-06-21T00:00:00Z",
          payload_json: { status: "completed" },
        },
      ]),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(await response.text()).toContain("event: scan_completed");
  });
});
