import { neon } from "@neondatabase/serverless";

export type SqlValue = string | number | boolean | null;
export type SqlRow = Record<string, unknown>;
export type SqlClient = (query: string, params?: SqlValue[]) => Promise<SqlRow[]>;

export interface Env {
  DATABASE_URL?: string;
}

export function createSqlClient(env: Env): SqlClient {
  if (!env.DATABASE_URL) {
    throw new ApiError(503, "DATABASE_URL is not configured");
  }
  const sql = neon(env.DATABASE_URL);
  return (query, params = []) => sql.query(query, params);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}
