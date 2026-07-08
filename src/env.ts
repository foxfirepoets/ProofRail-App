import { config } from "node:process";

export type EnvMap = Record<string, string | undefined>;

export function applyDatabaseUrlAliases(env: EnvMap = process.env): void {
  const supabaseUrl = normalizeSupabaseConnectionString(env.SUPABASE_DIRECT_CONNECTION_STRING, env.SUPABASE_PROJECT_ID);
  env.DATABASE_URL ||= supabaseUrl;
  env.DIRECT_URL ||= supabaseUrl || env.DATABASE_URL;
}

export function requiredEnv(name: string, env: EnvMap = process.env): string {
  const value = env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export function envPresence(names: string[], env: EnvMap = process.env): Record<string, boolean> {
  return Object.fromEntries(names.map((name) => [name, Boolean(env[name])]));
}

export function normalizeSupabaseConnectionString(value?: string, projectId?: string): string | undefined {
  if (!value) return value;
  try {
    const url = new URL(value);
    if (url.pathname === "/postgress") {
      url.pathname = "/postgres";
    }
    if (projectId && /^db\.[a-z0-9]+\.supabase\.co$/i.test(url.hostname)) {
      url.hostname = `db.${projectId}.supabase.co`;
    }
    return url.toString();
  } catch {
    return value;
  }
}

void config;
