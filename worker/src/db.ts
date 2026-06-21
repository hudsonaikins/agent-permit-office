import pg from "pg";

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
  return async (query, params = []) => {
    const client = new pg.Client({ connectionString: env.DATABASE_URL });
    await client.connect();
    try {
      const result = await client.query(query, params);
      return result.rows as SqlRow[];
    } finally {
      await client.end();
    }
  };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}
