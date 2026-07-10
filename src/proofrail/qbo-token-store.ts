import pg from "pg";

const { Pool } = pg;

/**
 * Durable storage for the MCP app's OWN Intuit OAuth grant - deliberately separate from
 * ProofRailRepository (business data: intakes/draws/fees/audit) because this is auth
 * infrastructure with a different lifecycle and a much sharper blast radius if mishandled.
 * See docs/QBO_MCP_OAUTH_APPROVAL.md for the full "why a separate grant" rationale: Intuit
 * rotates the refresh token on every refresh, so this app's tokens must never be the same
 * value as the work-machine scripts/*.py pipeline's tokens (.env QB_*_REFRESH_TOKEN) - the two
 * are independent OAuth grants against the same registered app, stored in independent places.
 *
 * Table: proofrail_qbo_token_store (already provisioned in the "Summa Terra Co-Work Automation"
 * Supabase project, fdnwlcomuddzmluvbylg - confirmed present 2026-07-09, columns: realm (PK,
 * text - the slot 'A' or 'B'), realm_id (text - the actual QBO company realmId), refresh_token
 * (text), access_token (text, nullable), access_expires_at (timestamptz, nullable),
 * updated_at (timestamptz, default now()). This module never creates the table - it only reads
 * and writes rows into the pre-existing schema.
 */
export type QboRealmSlot = "A" | "B";

export interface QboTokenRow {
  realm: QboRealmSlot;
  realmId: string;
  refreshToken: string;
  accessToken?: string;
  accessExpiresAt?: Date;
  updatedAt: Date;
}

export class QboTokenStore {
  private readonly pool: pg.Pool;

  constructor(connectionString?: string) {
    const cs = connectionString ?? process.env.PROOFRAIL_DATABASE_URL;
    if (!cs) {
      throw new Error(
        "PROOFRAIL_DATABASE_URL is not set. QboTokenStore must point at the same 'Summa Terra " +
          "Co-Work Automation' Supabase project (fdnwlcomuddzmluvbylg) as PostgresProofRailRepository.",
      );
    }
    this.pool = new Pool({ connectionString: cs, ssl: { rejectUnauthorized: false } });
  }

  async close(): Promise<void> {
    await this.pool.end();
  }

  async get(realm: QboRealmSlot): Promise<QboTokenRow | undefined> {
    const { rows } = await this.pool.query(
      `select realm, realm_id, refresh_token, access_token, access_expires_at, updated_at
       from proofrail_qbo_token_store where realm = $1`,
      [realm],
    );
    const r = rows[0];
    if (!r) return undefined;
    return {
      realm: r.realm,
      realmId: r.realm_id,
      refreshToken: r.refresh_token,
      accessToken: r.access_token ?? undefined,
      accessExpiresAt: r.access_expires_at ? new Date(r.access_expires_at) : undefined,
      updatedAt: new Date(r.updated_at),
    };
  }

  /**
   * Seed or fully replace a realm's grant - used once per realm by the /auth/qbo/callback route
   * after a fresh Intuit consent flow. Overwrites any prior row for that realm slot outright
   * (a fresh consent flow means the operator explicitly intends to replace the grant).
   */
  async seed(row: { realm: QboRealmSlot; realmId: string; refreshToken: string; accessToken?: string; accessExpiresAt?: Date }): Promise<void> {
    await this.pool.query(
      `insert into proofrail_qbo_token_store (realm, realm_id, refresh_token, access_token, access_expires_at, updated_at)
       values ($1, $2, $3, $4, $5, now())
       on conflict (realm) do update set
         realm_id = excluded.realm_id, refresh_token = excluded.refresh_token,
         access_token = excluded.access_token, access_expires_at = excluded.access_expires_at,
         updated_at = now()`,
      [row.realm, row.realmId, row.refreshToken, row.accessToken ?? null, row.accessExpiresAt ?? null],
    );
  }

  /**
   * Persist a rotated refresh token from an in-flight RealQboClient refresh (RealQboClient.token()
   * always gets a new refresh_token from Intuit on every call - losing this write breaks the NEXT
   * refresh). Never changes realm_id - a rotation is never a re-authorization against a different
   * company; if realm_id needs to change, that's a new consent flow via seed(), not a rotation.
   */
  async persistRotation(realm: QboRealmSlot, refreshToken: string, accessToken: string, accessExpiresAt: Date): Promise<void> {
    await this.pool.query(
      `update proofrail_qbo_token_store
       set refresh_token = $2, access_token = $3, access_expires_at = $4, updated_at = now()
       where realm = $1`,
      [realm, refreshToken, accessToken, accessExpiresAt],
    );
  }
}
