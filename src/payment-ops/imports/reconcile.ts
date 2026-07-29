import type { PaymentSourceRecord, ReconciliationRecord, ReconciliationResult } from "./types.js";

const norm = (value?: string): string => (value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const tokens = (value?: string): Set<string> => new Set(norm(value).split(" ").filter((token) => token.length > 2 && !["llc", "the", "from", "loan", "payment"].includes(token)));
const overlap = (left?: string, right?: string): number => {
  const a = tokens(left); const b = tokens(right);
  let count = 0;
  for (const token of a) if (b.has(token)) count += 1;
  return count;
};
const entityCompatible = (left?: string, right?: string): boolean => {
  const a = norm(left); const b = norm(right);
  if (a.includes("12sb") && b.includes("12sb")) return true;
  if ((a.includes("hunter") || a.includes("hln")) && (b.includes("hunter") || b.includes("hln"))) return true;
  return overlap(left, right) > 0;
};
const accountTokens = (record?: PaymentSourceRecord): string[] => {
  if (!record) return [];
  return [record.lastFour, record.accountNumber, record.payFromAccount, record.payFromBank].filter(Boolean).map((value) => norm(value));
};

const accountConflict = (master?: PaymentSourceRecord, calendar?: PaymentSourceRecord): string[] => {
  if (!master || !calendar) return [];
  const masterLastFour = norm(master.lastFour);
  const calendarLastFour = norm(calendar.lastFour);
  const conflicts: string[] = [];
  if (masterLastFour && calendarLastFour && masterLastFour !== calendarLastFour) {
    conflicts.push(`pay-from last-four conflict: master=${master.lastFour}, calendar=${calendar.lastFour}`);
  }
  if (norm(master.entity).includes("12sb") && masterLastFour && calendarLastFour && masterLastFour !== calendarLastFour) {
    conflicts.push("12SB account identity conflict quarantined; no account identity guess permitted");
  }
  const masterTokens = accountTokens(master);
  const calendarTokens = accountTokens(calendar);
  if (masterTokens.length && calendarTokens.length && masterTokens[0] !== calendarTokens[0] && !masterLastFour && !calendarLastFour) {
    conflicts.push("pay-from account identity differs across sources");
  }
  return conflicts;
};

const amountConflict = (master?: PaymentSourceRecord, calendar?: PaymentSourceRecord): string[] => {
  if (master?.amount === undefined || calendar?.amount === undefined) return [];
  return Math.abs(master.amount - calendar.amount) > 0.01
    ? [`amount conflict: master=${master.amount}, calendar=${calendar.amount}`]
    : [];
};

export const reconcilePaymentSources = (
  masterRecords: PaymentSourceRecord[],
  calendarRecords: PaymentSourceRecord[],
): ReconciliationResult => {
  const masterByKey = new Map<string, PaymentSourceRecord[]>();
  const calendarByKey = new Map<string, PaymentSourceRecord[]>();
  for (const record of masterRecords) (masterByKey.get(record.matchKey) ?? masterByKey.set(record.matchKey, []).get(record.matchKey)!).push(record);
  for (const record of calendarRecords) (calendarByKey.get(record.matchKey) ?? calendarByKey.set(record.matchKey, []).get(record.matchKey)!).push(record);
  const keys = new Set([...masterByKey.keys(), ...calendarByKey.keys()]);
  const unmatchedMasters = new Set(masterRecords.map((record) => record.sourceId));
  const unmatchedCalendars = new Set(calendarRecords.map((record) => record.sourceId));
  const fuzzyPairs = new Map<string, PaymentSourceRecord>();
  for (const calendar of calendarRecords) {
    if (masterByKey.has(calendar.matchKey)) continue;
    const candidates = masterRecords.filter((master) => entityCompatible(master.entity, calendar.entity)
      && overlap(master.payee, calendar.payee) > 0
      && (overlap(master.obligation, calendar.obligation) > 0 || overlap(master.payee, calendar.obligation) > 0));
    if (candidates.length === 1) fuzzyPairs.set(calendar.matchKey, candidates[0]);
  }
  const records: ReconciliationRecord[] = [];
  const quarantined: ReconciliationResult["quarantined"] = [];
  let matched = 0; let missingFromMaster = 0; let missingFromCalendar = 0; let conflicts = 0; let duplicates = 0;
  for (const matchKey of keys) {
    const masters = masterByKey.get(matchKey) ?? [];
    const calendars = calendarByKey.get(matchKey) ?? [];
    if (masters.length > 1 || calendars.length > 1) {
      duplicates += Math.max(0, masters.length - 1) + Math.max(0, calendars.length - 1);
      records.push({ matchKey, status: "DUPLICATE", master: masters[0], calendar: calendars[0], conflicts: ["multiple source rows share the same normalized obligation key"] });
      continue;
    }
    let master: PaymentSourceRecord | undefined = masters[0]; const calendar = calendars[0];
    if (!master && calendar) {
      master = fuzzyPairs.get(calendar.matchKey);
      if (master) {
        unmatchedMasters.delete(master.sourceId);
        unmatchedCalendars.delete(calendar.sourceId);
      }
    } else if (master) {
      unmatchedMasters.delete(master.sourceId);
    }
    if (calendar) unmatchedCalendars.delete(calendar.sourceId);
    if (!master) { missingFromMaster += 1; records.push({ matchKey, status: "MISSING_FROM_MASTER", calendar, conflicts: [] }); continue; }
    if (!calendar) { missingFromCalendar += 1; records.push({ matchKey, status: "MISSING_FROM_CALENDAR", master, conflicts: [] }); continue; }
    const foundConflicts = [...accountConflict(master, calendar), ...amountConflict(master, calendar)];
    if (foundConflicts.length) {
      conflicts += 1;
      records.push({ matchKey, status: "CONFLICT", master, calendar, conflicts: foundConflicts });
      quarantined.push({ matchKey, reason: foundConflicts.join("; "), sources: [master.sourceId, calendar.sourceId] });
    } else { matched += 1; records.push({ matchKey, status: "MATCHED", master, calendar, conflicts: [] }); }
  }
  return { records, matched, missingFromMaster, missingFromCalendar, conflicts, duplicates, quarantined };
};
