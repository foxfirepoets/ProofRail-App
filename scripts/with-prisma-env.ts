import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const env = { ...process.env };
const envPath = resolve(".env");

if (existsSync(envPath)) {
  const contents = readFileSync(envPath, "utf8");
  for (const line of contents.split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    env[key.trim()] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
  }
}

env.DATABASE_URL ||= env.SUPABASE_DIRECT_CONNECTION_STRING;
env.DIRECT_URL ||= env.SUPABASE_DIRECT_CONNECTION_STRING || env.DATABASE_URL;
for (const key of ["DATABASE_URL", "DIRECT_URL"]) {
  const value = env[key];
  if (!value) continue;
  try {
    const url = new URL(value);
    if (url.pathname === "/postgress") {
      url.pathname = "/postgres";
    }
    if (env.SUPABASE_PROJECT_ID && /^db\.[a-z0-9]+\.supabase\.co$/i.test(url.hostname)) {
      url.hostname = `db.${env.SUPABASE_PROJECT_ID}.supabase.co`;
    }
    env[key] = url.toString();
  } catch {
    // Leave non-URL values untouched; Prisma will report the real validation error.
  }
}

const [command, ...args] = process.argv.slice(2);
if (!command) {
  throw new Error("Usage: tsx scripts/with-prisma-env.ts <command> [...args]");
}

const executable = process.platform === "win32" && !command.endsWith(".cmd") ? `${command}.cmd` : command;
const result = spawnSync(executable, args, {
  stdio: "inherit",
  env,
  shell: true,
});

if (result.error) {
  console.error(result.error.message);
}

process.exit(result.status ?? 1);
