export type WorkbookKind = "MASTER_REGISTER" | "PAYMENT_CALENDAR";

export type ReconciliationStatus =
  | "MATCHED"
  | "MISSING_FROM_MASTER"
  | "MISSING_FROM_CALENDAR"
  | "CONFLICT"
  | "DUPLICATE";

export interface PaymentSourceRecord {
  source: "MASTER_REGISTER" | "PAYMENT_CALENDAR";
  sourceId: string;
  rowNumber: number;
  matchKey: string;
  entity: string;
  obligation: string;
  payee: string;
  dueDate?: string;
  payFromBank?: string;
  payFromAccount?: string;
  accountNumber?: string;
  lastFour?: string;
  amount?: number;
  amountText?: string;
  paymentMethod?: string;
  operator?: string;
  approval?: string;
  status?: string;
  sourceRow: Record<string, unknown>;
  duplicateOf?: string;
}

export interface WorkbookImportResult {
  kind: WorkbookKind;
  sheetName: string;
  headerRowIndex: number;
  filePath?: string;
  fileHash?: string;
  records: PaymentSourceRecord[];
  duplicates: Array<{ sourceId: string; duplicateOf: string; rowNumber: number }>;
  warnings: string[];
}

export interface ReconciliationRecord {
  matchKey: string;
  status: ReconciliationStatus;
  master?: PaymentSourceRecord;
  calendar?: PaymentSourceRecord;
  conflicts: string[];
}

export interface ReconciliationResult {
  records: ReconciliationRecord[];
  matched: number;
  missingFromMaster: number;
  missingFromCalendar: number;
  conflicts: number;
  duplicates: number;
  quarantined: Array<{ matchKey: string; reason: string; sources: string[] }>;
}
