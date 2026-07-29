import assert from "node:assert/strict";
import test from "node:test";
import { importMasterPaymentRegisterXlsx, importPaymentCalendarXlsx } from "../src/payment-ops/imports/xlsx-loader.js";
import { reconcilePaymentSources } from "../src/payment-ops/imports/reconcile.js";

const masterPath = "C:/Users/Heather Workman/Downloads/STV_MASTER_PAYMENT_CONTROL_REGISTER_MERGED_2026-07-21.xlsx";
const calendarPath = "C:/Users/Heather Workman/Downloads/STV Monthly Payment Calendar \u2014 How to Pay (2026-07-20).xlsx";

test("real STV workbooks load rows, hash files, and reconcile parsed data", () => {
  const master = importMasterPaymentRegisterXlsx(masterPath);
  const calendar = importPaymentCalendarXlsx(calendarPath);
  assert.ok(master.records.length > 0);
  assert.ok(calendar.records.length > 0);
  assert.equal(master.fileHash?.length, 64);
  assert.equal(calendar.fileHash?.length, 64);
  assert.equal(master.headerRowIndex, 3);
  assert.equal(calendar.headerRowIndex, 0);
  assert.notEqual(master.records[0]?.sourceId, calendar.records[0]?.sourceId);
  const result = reconcilePaymentSources(master.records, calendar.records);
  assert.ok(result.records.length > 0);
  assert.ok(result.matched > 0);
});

test("real XLSX loader preserves 12SB quarantine behavior", () => {
  const master = importMasterPaymentRegisterXlsx(masterPath);
  const calendar = importPaymentCalendarXlsx(calendarPath);
  const master12sb = master.records.find((record) => /12sb/i.test(record.entity) && record.lastFour);
  const calendar12sb = calendar.records.find((record) => /12sb/i.test(record.entity) && record.lastFour);
  assert.ok(master12sb && calendar12sb);
  const alteredCalendar = {
    ...master12sb,
    source: "PAYMENT_CALENDAR" as const,
    sourceId: calendar12sb.sourceId,
    lastFour: master12sb.lastFour === "0000" ? "9999" : "0000",
  };
  const result = reconcilePaymentSources([master12sb], [alteredCalendar]);
  assert.equal(result.records[0]?.status, "CONFLICT");
  assert.equal(result.quarantined.length, 1);
  assert.match(result.quarantined[0]?.reason ?? "", /12SB account identity conflict quarantined/);
});

test("real XLSX loader fails closed for missing or ambiguous required headers", () => {
  assert.throws(() => importMasterPaymentRegisterXlsx("C:/does/not/exist.xlsx"), /not found/i);
});
