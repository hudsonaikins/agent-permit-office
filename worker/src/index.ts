import { handleRequest } from "./api";
import type { Env } from "./db";

export default {
  fetch(request, env, _ctx) {
    return handleRequest(request, env);
  },
} satisfies ExportedHandler<Env>;
