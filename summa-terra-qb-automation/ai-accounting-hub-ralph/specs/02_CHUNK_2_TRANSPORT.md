# CHUNK_2_TRANSPORT: Build the async QBWC SOAP endpoint and qbXML codec that reads one company file into the canonical store.

## Summary

Builds the thin, swappable transport adapter: an outbound-poll QuickBooks Web Connector (QBWC) SOAP endpoint and a qbXML codec (forked from the MIT selfjared1/quickbooks_desktop pattern) behind a stable adapter interface. This chunk performs the CRUX spike — measuring real QBWC poll cadence and queue depth — and a read-only sync of ONE company file's vendors and bills into the canonical store with `raw_extensions` preserved losslessly. It comes after INFRA because it writes the canonical schema, and hands a populated store to CHUNK_3_CANONICAL.

## Acceptance Criteria

- [ ] A QBWC-compliant SOAP endpoint implements `authenticate`, `sendRequestXML`, `receiveResponseXML`, `getLastError`, `closeConnection`.
- [ ] A `.qwc` config can register the endpoint; `QBWC_USERNAME`/`QBWC_PASSWORD` auth works.
- [ ] qbXML `VendorQuery` and `BillQuery` requests are emitted and responses parsed into canonical `vendors`/`bills` rows.
- [ ] `qb_list_id`, `qb_txn_id`, and `qb_edit_sequence` are captured; all QB-native fields not in the canonical schema are preserved in `raw_extensions` (lossless round-trip assertion).
- [ ] Adapter sits behind an interface (`AccountingAdapter`) so a future QBO/Intacct adapter can replace it without touching callers.
- [ ] A `/sync/health` style metric records poll cadence and max queue depth (the CRUX measurement).
- [ ] Read-only only — no qbXML write/add requests in this chunk.
- [ ] All tests pass with zero failures.

## Endpoints / Interfaces

| Method | Path | Description |
|--------|------|-------------|
| POST | /qbwc | QBWC SOAP endpoint (authenticate/sendRequestXML/receiveResponseXML/getLastError/closeConnection) |

Internal: `AccountingAdapter` interface (read methods: `list_vendors`, `list_bills`) with a `QBDesktopAdapter` implementation.

## Database Changes

No schema changes in this chunk (writes rows into `companies`, `vendors`, `bills` created by CHUNK_1_INFRA).

## Test Scenarios

- **Happy path**: a mocked QBWC session returns qbXML vendor+bill responses; rows land in the canonical store with `raw_extensions` populated.
- **Edge case**: a qbXML response with a field absent from the canonical schema is preserved verbatim in `raw_extensions` (no data loss).
- **Failure case**: QB file locked / `getLastError` returns an error → poll backs off and retries; no partial/corrupt rows committed.
- **Integration**: CHUNK_3_CANONICAL can query the synced vendors/bills and the recorded poll-cadence metric.

## Dependencies

- **Requires**: CHUNK_1_INFRA
- **Blocks**: CHUNK_3_CANONICAL, CHUNK_6_VERIFY (write-back extends this adapter)

## Completion Promise

<promise>CHUNK COMPLETE: CHUNK_2_TRANSPORT</promise>
