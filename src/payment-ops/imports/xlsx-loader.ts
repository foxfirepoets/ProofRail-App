import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import type { WorkbookImportResult, WorkbookKind } from "./types.js";
import { importMasterPaymentRegister, importPaymentCalendar } from "./workbook-adapters.js";

export interface XlsxImportOptions {
  filePath: string;
  sheetName: string;
}

type XlsxCell = string | number | boolean | null;

const PYTHON_READER = [
  "import json,sys,openpyxl",
  "path,sheet=sys.argv[1],sys.argv[2]",
  "wb=openpyxl.load_workbook(path,read_only=True,data_only=True)",
  "if sheet not in wb.sheetnames: raise ValueError('Requested sheet not found: '+sheet)",
  "ws=wb[sheet]",
  "def cell(v):",
  "    if v is None: return None",
  "    if hasattr(v,'isoformat'): return v.isoformat()",
  "    return v",
  "print(json.dumps([[cell(v) for v in row] for row in ws.iter_rows(values_only=True)], ensure_ascii=False))",
].join("\n");

const readRows = ({ filePath, sheetName }: XlsxImportOptions): XlsxCell[][] => {
  if (!existsSync(filePath)) throw new Error(`XLSX file not found: ${filePath}`);
  try {
    const output = execFileSync(process.env.PYTHON ?? "python", ["-c", PYTHON_READER, filePath, sheetName], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    const parsed: unknown = JSON.parse(output);
    if (!Array.isArray(parsed) || parsed.some((row) => !Array.isArray(row))) throw new Error("Spreadsheet reader returned invalid rows");
    return parsed as XlsxCell[][];
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Fail-closed XLSX read for ${filePath} / ${sheetName}: ${detail}`);
  }
};

const normalizeHeader = (value: unknown): string => String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const requiredAliases: Record<string, string[]> = {
  entity: ["entity", "paying entity"],
  obligation: ["obligation", "bill account", "bill account", "bill obligation", "payment obligation"],
  payee: ["payee lender", "payee", "lender", "counterparty destination"],
};

const validateRequiredHeaders = (rows: XlsxCell[][]): void => {
  const header = rows.find((row) => Object.values(requiredAliases).every((aliases) => row.map(normalizeHeader).some((cell) => aliases.includes(cell))));
  if (!header) throw new Error("Missing required workbook headers: entity, obligation, payee");
  for (const [field, aliases] of Object.entries(requiredAliases)) {
    const matches = header.map(normalizeHeader).filter((cell) => aliases.includes(cell));
    if (matches.length !== 1) throw new Error(`Ambiguous required workbook header ${field}: found ${matches.length} matches`);
  }
};

export const importXlsxWorkbook = (kind: WorkbookKind, options: XlsxImportOptions): WorkbookImportResult => {
  if (!existsSync(options.filePath)) throw new Error(`XLSX file not found: ${options.filePath}`);
  const bytes = readFileSync(options.filePath);
  const fileHash = createHash("sha256").update(bytes).digest("hex");
  const rows = readRows(options);
  validateRequiredHeaders(rows);
  const result = kind === "MASTER_REGISTER"
    ? importMasterPaymentRegister(rows, options.sheetName)
    : importPaymentCalendar(rows, options.sheetName);
  return { ...result, filePath: options.filePath, fileHash };
};

export const importMasterPaymentRegisterXlsx = (filePath: string): WorkbookImportResult =>
  importXlsxWorkbook("MASTER_REGISTER", { filePath, sheetName: "Master Bill Register" });

export const importPaymentCalendarXlsx = (filePath: string): WorkbookImportResult =>
  importXlsxWorkbook("PAYMENT_CALENDAR", { filePath, sheetName: "Payment Calendar" });
