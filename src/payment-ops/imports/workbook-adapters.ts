import { createHash } from "node:crypto";
import type { PaymentSourceRecord, WorkbookImportResult, WorkbookKind } from "./types.js";

type Cell = unknown;
type Row = Cell[];

const clean = (value: Cell): string => String(value ?? "").trim();
const key = (value: Cell): string => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const aliases: Record<string, string[]> = {
  entity: ["entity", "paying entity"],
  obligation: ["obligation", "bill account", "bill / account", "bill obligation", "payment obligation"],
  payee: ["payee lender", "payee", "lender", "counterparty destination"],
  dueDate: ["next expected due", "payment due date", "payment / due date", "due action date", "date due"],
  payFromBank: ["pay from bank", "pays from bank", "pay from account"],
  payFromAccount: ["pays from account as shown online", "pays from account", "account name", "pay from account"],
  accountNumber: ["account", "account number", "account #"],
  lastFour: ["last 4", "acct last 4", "acct last-4", "last four"],
  amount: ["expected amount", "approx amount", "amount"],
  paymentMethod: ["payment method", "how paid"],
  operator: ["target operator", "who pays", "observed operator", "payment operator"],
  approval: ["mike approval", "approval needed", "approval needed?"],
  status: ["current status", "status 2026 07 20", "status as of 2026 07 20", "status"],
};

const findHeader = (headers: string[], field: keyof typeof aliases): number => {
  const normalized = headers.map(key);
  return normalized.findIndex((header) => aliases[field].some((alias) => key(alias) === header));
};

const firstNonEmptyRow = (rows: Row[]): number => rows.findIndex((row) => row.some((cell) => clean(cell) !== ""));

const parseAmount = (value: Cell): number | undefined => {
  const text = clean(value).replace(/[$,]/g, "");
  if (!text || /unknown|see |variable|confirm|get /i.test(text)) return undefined;
  const match = text.match(/-?\d+(?:\.\d+)?/);
  if (!match) return undefined;
  const amount = Number(match[0]);
  return Number.isFinite(amount) ? amount : undefined;
};

const parseDate = (value: Cell): string | undefined => {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value.toISOString().slice(0, 10);
  const text = clean(value);
  const match = text.match(/\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b/);
  if (!match) return undefined;
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
};

const normalizedLastFour = (value: Cell): string | undefined => {
  if (typeof value === "number" && Number.isInteger(value)) return String(value).padStart(4, "0");
  const values = clean(value).match(/\d{4}/g) ?? [];
  return values.length === 1 ? values[0].padStart(4, "0") : values.length > 1 ? values.join("/") : undefined;
};

const stableId = (kind: WorkbookKind, row: Record<string, unknown>, rowNumber: number, fileHash?: string): string => {
  const explicit = clean(row["Bill ID"] ?? row["Source ID"]);
  const identity = explicit || [row["Entity"], row["Obligation"], row["Payee / Lender"], row["Payment / Due Date"], row["Last 4"]].map(clean).join("|");
  const digest = createHash("sha256").update(`${kind}|${fileHash ?? "normalized"}|${identity}`).digest("hex").slice(0, 20);
  return `${kind.toLowerCase()}-${digest || rowNumber}`;
};

const matchKey = (entity: string, obligation: string, payee: string): string =>
  [entity, obligation, payee].map(key).filter(Boolean).join("|");

const importRows = (kind: WorkbookKind, sheetName: string, rows: Row[], options: { filePath?: string; fileHash?: string } = {}): WorkbookImportResult => {
  const headerRowIndex = rows.findIndex((row) => {
    const headers = row.map(clean);
    return ["entity", "obligation", "payee"].every((field) => findHeader(headers, field as keyof typeof aliases) >= 0);
  });
  if (headerRowIndex < 0) return { kind, sheetName, headerRowIndex: -1, records: [], duplicates: [], warnings: ["No non-empty header row found."] };
  const headers = rows[headerRowIndex].map(clean);
  const indexes = Object.fromEntries(Object.keys(aliases).map((field) => [field, findHeader(headers, field as keyof typeof aliases)])) as Record<string, number>;
  const required = ["entity", "obligation", "payee"];
  const warnings = required.filter((field) => indexes[field] < 0).map((field) => `Missing expected column: ${field}`);
  if (warnings.length) throw new Error(`Workbook ${kind} is missing required headers: ${warnings.join(", ")}`);
  const records: PaymentSourceRecord[] = [];
  const duplicates: WorkbookImportResult["duplicates"] = [];
  const seen = new Map<string, PaymentSourceRecord>();
  for (let offset = headerRowIndex + 1; offset < rows.length; offset += 1) {
    const row = rows[offset];
    if (!row?.some((cell) => clean(cell) !== "")) continue;
    const sourceRow = Object.fromEntries(headers.map((header, index) => [header || `column_${index + 1}`, row[index]]));
    const read = (field: string): Cell => indexes[field] >= 0 ? row[indexes[field]] : undefined;
    const entity = clean(read("entity"));
    const obligation = clean(read("obligation"));
    const payee = clean(read("payee"));
    const record: PaymentSourceRecord = {
      source: kind,
      sourceId: stableId(kind, sourceRow, offset + 1, options.fileHash),
      rowNumber: offset + 1,
      matchKey: matchKey(entity, obligation, payee),
      entity,
      obligation,
      payee,
      dueDate: parseDate(read("dueDate")),
      payFromBank: clean(read("payFromBank")) || undefined,
      payFromAccount: clean(read("payFromAccount")) || undefined,
      accountNumber: clean(read("accountNumber")) || undefined,
      lastFour: normalizedLastFour(read("lastFour")),
      amount: parseAmount(read("amount")),
      amountText: clean(read("amount")) || undefined,
      paymentMethod: clean(read("paymentMethod")) || undefined,
      operator: clean(read("operator")) || undefined,
      approval: clean(read("approval")) || undefined,
      status: clean(read("status")) || undefined,
      sourceRow,
    };
    const prior = seen.get(record.sourceId);
    if (prior) {
      record.duplicateOf = prior.sourceId;
      duplicates.push({ sourceId: record.sourceId, duplicateOf: prior.sourceId, rowNumber: record.rowNumber });
    } else {
      seen.set(record.sourceId, record);
    }
    records.push(record);
  }
  return { kind, sheetName, headerRowIndex, filePath: options.filePath, fileHash: options.fileHash, records, duplicates, warnings };
};

export const importMasterPaymentRegister = (rows: Row[], sheetName = "Master Bill Register"): WorkbookImportResult => importRows("MASTER_REGISTER", sheetName, rows);
export const importPaymentCalendar = (rows: Row[], sheetName = "Payment Calendar"): WorkbookImportResult => importRows("PAYMENT_CALENDAR", sheetName, rows);

export const normalizeWorkbookRows = (rows: Row[]): Row[] => rows.map((row) => row.map((cell) => typeof cell === "string" ? cell.replace(/\u00a0/g, " ").trim() : cell));
