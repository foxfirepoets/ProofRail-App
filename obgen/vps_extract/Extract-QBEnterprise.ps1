<#
  Extract-QBEnterprise.ps1  -  RUN THIS ON THE RIGHTWORKS VPS (where QuickBooks Desktop lives)

  WHAT IT IS
    A READ-ONLY extract of ONE open QuickBooks Desktop Enterprise company file, via QODBC.
    It never writes to QuickBooks - it only runs SELECT / sp_report queries and saves CSV files.
    The CSVs it writes match exactly what the obgen migration tool expects, so once they sync
    back to Ben's PC on the J: dual-drive, obgen can build the QBO Advanced opening balances.

  WHAT IT PULLS (per open company file), into  <OutRoot>\<Entity>\ :
    trial_balance.csv   every account + debit/credit as of the cutover date  (the spine)
    open_ap.csv         unpaid bills (A/P)
    open_ap_lines.csv   the expense/item lines behind those bills
    open_ar.csv         unpaid invoices (A/R)
    cip_history.csv     construction-in-progress GL detail (for job/item rebuild)
    accounts_list.csv   the full chart of accounts (all accounts, even zero-balance)
    _meta.json          company name + timestamp + trial-balance totals & balance check

  HOW TO RUN (do this once per company file):
    1. In QuickBooks on the VPS, OPEN the entity's company file (QODBC reads whatever is OPEN).
    2. Open PowerShell **that matches your QODBC bitness** (see README - usually 32-bit:
       C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe).
    3. Run, passing the short entity key that matches obgen\config\entities.yaml:
         powershell -ExecutionPolicy Bypass -File .\Extract-QBEnterprise.ps1 -Entity 12SB
    4. Read the summary. If it says BALANCED and the row counts look right, you're done - the
       files are already on the J: drive syncing back to the PC. Repeat for the next file.

  SAFE: read-only. It cannot post, void, delete, or change anything in QuickBooks.
#>

param(
  [Parameter(Mandatory=$true)][string]$Entity,      # short key, e.g. 12SB  (names the output subfolder)
  [string]$Cutover    = "2026-06-30",               # balances as-of date (obgen cutover)
  [string]$CipAccount = "Development/Improvements",  # legacy account holding construction cost
  [string]$Dsn        = "QuickBooks Data",           # QODBC DSN name (default QODBC install)
  [string]$OutRoot    = (Join-Path $PSScriptRoot "_output")
)

$ErrorActionPreference = "Stop"
$bits = if ([Environment]::Is64BitProcess) { "64-bit" } else { "32-bit" }
Write-Host "=== Extract-QBEnterprise  (PowerShell is $bits) ==="

# ---- output folder ----
$dir = Join-Path $OutRoot $Entity
New-Item -ItemType Directory -Force -Path $dir | Out-Null

# ---- CSV helpers (RFC-4180 quoting) ----
function CsvCell($v) {
  if ($null -eq $v) { return "" }
  $s = [string]$v
  if ($s -match '[",\r\n]') { '"' + ($s -replace '"','""') + '"' } else { $s }
}
function Write-Csv([string[]]$headers, $rows, [string]$path) {
  $sw = New-Object System.IO.StreamWriter($path, $false, (New-Object System.Text.UTF8Encoding($false)))
  $sw.WriteLine((($headers | ForEach-Object { CsvCell $_ }) -join ","))
  foreach ($r in $rows) { $sw.WriteLine(((@($r) | ForEach-Object { CsvCell $_ }) -join ",")) }
  $sw.Close()
  Write-Host ("  -> {0}  ({1} rows)" -f (Split-Path $path -Leaf), @($rows).Count)
}

# ---- connect ----
$conn = New-Object System.Data.Odbc.OdbcConnection
$conn.ConnectionString = "DSN=$Dsn;"
try {
  $conn.Open()
} catch {
  Write-Host "`n! Could not connect to QODBC DSN '$Dsn'." -ForegroundColor Red
  Write-Host "  - Make sure QuickBooks is OPEN with the company file loaded."
  Write-Host "  - Make sure this PowerShell bitness ($bits) matches your QODBC driver's bitness."
  try { Write-Host "  Available DSNs:"; Get-OdbcDsn | Select-Object Name,DriverName,Platform | Format-Table | Out-String | Write-Host } catch {}
  throw
}

# Read query -> list of rows (each row = first $ncols columns as strings; $ncols=0 => all columns)
function Query-Rows([string]$sql, [int]$ncols) {
  $cmd = $conn.CreateCommand(); $cmd.CommandText = $sql; $cmd.CommandTimeout = 0
  $rd = $cmd.ExecuteReader()
  $rows = New-Object System.Collections.ArrayList
  $take = if ($ncols -gt 0) { [Math]::Min($ncols, $rd.FieldCount) } else { $rd.FieldCount }
  while ($rd.Read()) {
    $vals = @()
    for ($i = 0; $i -lt $take; $i++) {
      if ($rd.IsDBNull($i)) { $vals += "" } else { $vals += [string]$rd.GetValue($i) }
    }
    [void]$rows.Add($vals)
  }
  $rd.Close()
  return ,$rows
}
function To-Money([string]$s) {
  if ([string]::IsNullOrWhiteSpace($s)) { return 0.0 }
  $c = ($s -replace '[^0-9\.\-]', '')
  if ($c -eq '' -or $c -eq '-' -or $c -eq '.') { return 0.0 }
  return [double]$c
}

try {
  # ---- company identity (obgen pre-flight verifies this equals qbw_name) ----
  $cmd = $conn.CreateCommand(); $cmd.CommandText = "SELECT CompanyName FROM Company"
  $company = [string]$cmd.ExecuteScalar()
  Write-Host "  open company: '$company'   ->  entity '$Entity'"

  # ---- Trial Balance (the spine) ----  columns: Label, Debit, Credit
  $tb = Query-Rows "sp_report TrialBalance show Label, Debit, Credit parameters DateTo = {d'$Cutover'}" 3
  Write-Csv @("account","debit","credit") $tb (Join-Path $dir "trial_balance.csv")
  $dr = 0.0; $cr = 0.0
  foreach ($r in $tb) { $dr += To-Money $r[1]; $cr += To-Money $r[2] }

  # ---- Open A/P (unpaid bills) + their lines ----
  $ap = Query-Rows "SELECT TxnID, VendorRefFullName, TxnDate, DueDate, RefNumber, Memo, AmountDue FROM Bill WHERE IsPaid = 0" 7
  Write-Csv @("txn_id","vendor","date","due","refnum","memo","amount") $ap (Join-Path $dir "open_ap.csv")
  $apLines = New-Object System.Collections.ArrayList
  foreach ($b in $ap) {
    $txn = ($b[0] -replace "'","''")
    $lr = Query-Rows ("SELECT TxnID, ExpenseLineAccountRefFullName, ItemLineItemRefFullName, ExpenseLineAmount, ItemLineAmount, ExpenseLineMemo FROM BillExpenseLine WHERE TxnID = '$txn'") 6
    foreach ($x in $lr) { [void]$apLines.Add($x) }
  }
  Write-Csv @("txn_id","exp_account","item","exp_amt","item_amt","memo") $apLines (Join-Path $dir "open_ap_lines.csv")

  # ---- Open A/R (unpaid invoices) ----
  $ar = Query-Rows "SELECT TxnID, CustomerRefFullName, TxnDate, DueDate, RefNumber, BalanceRemaining FROM Invoice WHERE IsPaid = 0" 6
  Write-Csv @("txn_id","customer","date","due","refnum","balance") $ar (Join-Path $dir "open_ar.csv")

  # ---- CIP history (construction-in-progress GL detail) ----
  $cipAcctEsc = ($CipAccount -replace "'","''")
  $cip = Query-Rows ("sp_report GeneralLedger show TxnType, Date, RefNumber, Name, Memo, Account, Amount parameters DateFrom = {d'1900-01-01'}, DateTo = {d'$Cutover'}, AccountFilterFullName = '$cipAcctEsc'") 7
  Write-Csv @("txn_type","date","refnum","name","memo","account","amount") $cip (Join-Path $dir "cip_history.csv")

  # ---- Full chart of accounts (extra: catches zero-balance accounts for gap checks) ----
  $acc = Query-Rows "SELECT FullName, AccountType, AccountNumber, Balance FROM Account" 4
  Write-Csv @("full_name","type","acct_number","balance") $acc (Join-Path $dir "accounts_list.csv")

  # ---- meta + balance check ----
  $delta = [Math]::Round($dr - $cr, 2)
  $balanced = [Math]::Abs($delta) -lt 0.01
  $meta = [ordered]@{
    company      = $company
    entity       = $Entity
    cutover      = $Cutover
    extracted    = (Get-Date).ToString("o")
    tb_total_dr  = [Math]::Round($dr, 2)
    tb_total_cr  = [Math]::Round($cr, 2)
    tb_delta     = $delta
    tb_rows      = @($tb).Count
    open_ap_rows = @($ap).Count
    open_ar_rows = @($ar).Count
    powershell   = $bits
  }
  ($meta | ConvertTo-Json) | Set-Content -Path (Join-Path $dir "_meta.json") -Encoding UTF8

  Write-Host ""
  Write-Host ("  Trial balance: DR {0:N2}  CR {1:N2}  (delta {2:N2})" -f $dr, $cr, $delta)
  if (@($tb).Count -eq 0) {
    Write-Host "  ! WARNING: trial balance came back EMPTY - is the RIGHT company file open?" -ForegroundColor Yellow
  } elseif ($balanced) {
    Write-Host "  BALANCED. Extract complete for '$Entity'." -ForegroundColor Green
  } else {
    Write-Host "  ! NOT BALANCED (DR != CR). Note this and check the source before loading." -ForegroundColor Yellow
  }
  Write-Host ("  Files saved to: {0}" -f $dir)
  Write-Host "  (They're on the J: drive now, syncing back to the PC.)"
}
finally {
  $conn.Close()
}
