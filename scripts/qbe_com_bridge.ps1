<#
.SYNOPSIS
    Thin, single-purpose QuickBooks Desktop Enterprise COM bridge for the QBE
    WRITE path. This is the ONLY component that talks to QuickBooks.

.DESCRIPTION
    Mirrors the PROVEN read connection idiom used by scripts\qbw_bulk_extract.ps1
    and scripts\qbw_full_extract.ps1 (QBXMLRP2.RequestProcessor -> OpenConnection2
    -> BeginSession -> ProcessRequest, 29/29 clean sessions) but INVERTS the
    read-only preference so a JournalEntryAdd can commit.

    It does exactly one ProcessRequest per invocation: it reads a request-XML file
    produced by the Python layer (an Add request, or a read-back / duplicate-gate
    Query), sends it to the open company file, and writes the raw response XML to
    -OutputFile. It performs NO qbXML assembly and NO business logic -- Python owns
    all of that. Keeping this layer dumb keeps the write surface auditable.

    SAFETY GUARDS (each throws before any COM object is created):
      * -CompanyFile MUST resolve under the working-copies root. A path anywhere
        under the canonical "QB Enterpise Current Files" directory is REFUSED.
        This is the same canonical-path guard the read scripts enforce, kept
        intact for the writer.
      * Write mode (-ReadOnly:$false) additionally requires the QBE_POST_LIVE=1
        environment variable AND the -IUnderstandThisWrites switch. Absent either,
        the script refuses. The Python driver never sets these in dry-run.
      * The default mode is READ-ONLY (used by the duplicate gate and read-back),
        matching the read scripts' PutIsReadOnly(true).

.NOTES
    This script is authored and unit-covered by the offline test suite via a stub;
    it is NOT executed live during the build task. The live smoke test
    (docs\QBE_LIVE_SMOKE_TEST_RUNBOOK.md) is the first and only time it runs for
    real, against a WORKING COPY, driven by a human who has approved the cert.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$CompanyFile,

    [Parameter(Mandatory = $true)]
    [string]$RequestFile,

    [Parameter(Mandatory = $true)]
    [string]$OutputFile,

    [string]$AppName = "Summa Terra QBE Posting Bridge",

    # READ-ONLY IS THE DEFAULT. A bare -Write switch opts into a write session.
    # We use -Write (present/absent) rather than -ReadOnly:$false because PowerShell
    # cannot bind "-ReadOnly:$false" when the script is invoked via `powershell -File`
    # (it throws "Cannot convert value System.String to SwitchParameter"). A bare
    # -Write passes cleanly through -File, so the driver can actually write.
    [switch]$Write,

    # Explicit human acknowledgement required for any write session.
    [switch]$IUnderstandThisWrites
)

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------- #
# Path guards (identical spirit to the proven read scripts)
# --------------------------------------------------------------------------- #
$canonicalRoot = [IO.Path]::GetFullPath("C:\Users\Heather Workman\Desktop\QB Enterpise Current Files")
$workingRoot   = [IO.Path]::GetFullPath("C:\Users\Heather Workman\Desktop\QBW Migration Workspace\working-copies")
$companyPath   = [IO.Path]::GetFullPath($CompanyFile)

# Default-deny for canonical live-books. NARROW per-file exception: the bridge
# allows EXACTLY ONE canonical file per run -- the one whose full path equals
# $env:QBE_ALLOW_CANONICAL. Ben authorized this per entity (2026-07-22, verbatim:
# "lifting the working-copies guard for Freeman only"). Every other canonical path
# is still refused; a non-working-copy path is refused unless it is that one file.
$allowCanonical = ""
if ($env:QBE_ALLOW_CANONICAL) { $allowCanonical = [IO.Path]::GetFullPath($env:QBE_ALLOW_CANONICAL) }
$isAllowedCanonical = ($allowCanonical -ne "") -and ($companyPath.Equals($allowCanonical, [StringComparison]::OrdinalIgnoreCase))
if ($isAllowedCanonical) { Write-Warning "CANONICAL LIVE-BOOKS WRITE AUTHORIZED for exactly: $companyPath" }

if ($companyPath.StartsWith($canonicalRoot, [StringComparison]::OrdinalIgnoreCase) -and (-not $isAllowedCanonical)) {
    throw "REFUSED: CompanyFile is under the canonical live-books directory ($canonicalRoot). This bridge opens a canonical file only when its exact path is set in QBE_ALLOW_CANONICAL."
}
if ((-not $companyPath.StartsWith($workingRoot, [StringComparison]::OrdinalIgnoreCase)) -and (-not $isAllowedCanonical)) {
    throw "REFUSED: CompanyFile must be a working copy under $workingRoot (or the exact canonical file named in QBE_ALLOW_CANONICAL)"
}
if (-not (Test-Path -LiteralPath $companyPath -PathType Leaf)) {
    throw "Working-copy company file not found: $companyPath"
}
if (-not (Test-Path -LiteralPath $RequestFile -PathType Leaf)) {
    throw "Request file not found: $RequestFile"
}

$writeSession = [bool]$Write
if ($writeSession) {
    if ($env:QBE_POST_LIVE -ne "1") {
        throw "REFUSED: write session requires environment variable QBE_POST_LIVE=1"
    }
    if (-not $IUnderstandThisWrites) {
        throw "REFUSED: write session requires the -IUnderstandThisWrites switch"
    }
}

$request = [IO.File]::ReadAllText($RequestFile)

# --------------------------------------------------------------------------- #
# Interop assembly + AuthPreferences (reflection, same as read scripts)
# --------------------------------------------------------------------------- #
$interopPath = "C:\Program Files\Intuit\QuickBooks Enterprise Solutions 24.0\Interop.QBXMLRP2Lib.dll"
if (-not (Test-Path -LiteralPath $interopPath -PathType Leaf)) {
    throw "QuickBooks Enterprise 24 interop library not found: $interopPath"
}
$interopAssembly = [Reflection.Assembly]::LoadFrom($interopPath)
$authType = $interopAssembly.GetType("Interop.QBXMLRP2Lib.IAuthPreferences", $true)

$processor = $null
$auth = $null
$ticket = $null
$sessionOpen = $false
$connectionOpen = $false
$localQbdLaunchUi = 3   # localQBDLaunchUI
$openDoNotCare = 2      # qbFileOpenDoNotCare

# Stable AppID for OpenConnection2 (BUG 6: certificate dialog re-prompted on every
# single connection during the first live post, 2026-07-23 -- see MEMORY.md session
# log). This bridge opens ONE brand-new connection per qbXML request (by design --
# see the file header), so a single post can make 4+ separate connections. QuickBooks'
# "Yes, always allow" grant is meant to persist per-application across connections;
# a blank appID gives QuickBooks no stable identity to key that persisted grant to.
# Fixed GUID, must never change (a changed GUID = a "new" app to QuickBooks, forcing
# re-approval on every entity's canonical file all over again).
$stableAppId = "6F3A9E12-8B44-4C1D-9A2E-5D7F1B3C8E60"

try {
    $processor = New-Object -ComObject "QBXMLRP2.RequestProcessor"
    $auth = $processor.AuthPreferences

    # THE INVERSION: a -Write session clears read-only; the default keeps it.
    # Everything else matches the proven read connection exactly.
    $authType.GetMethod("PutIsReadOnly").Invoke($auth, @([bool](-not $Write)))
    $authType.GetMethod("PutUnattendedModePref").Invoke($auth, @(1)) # umpRequired
    $authType.GetMethod("PutPersonalDataPref").Invoke($auth, @(3))   # pdpNotNeeded

    $processor.OpenConnection2($stableAppId, $AppName, $localQbdLaunchUi)
    $connectionOpen = $true
    $ticket = $processor.BeginSession($companyPath, $openDoNotCare)
    $sessionOpen = $true

    $response = $processor.ProcessRequest($ticket, $request)

    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($OutputFile))
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    [IO.File]::WriteAllText($OutputFile, $response, [Text.UTF8Encoding]::new($false))

    [xml]$xml = $response
    $node = $xml.QBXML.QBXMLMsgsRs.ChildNodes | Select-Object -First 1
    [pscustomobject]@{
        company_file    = $companyPath
        read_only       = [bool](-not $Write)
        response_type   = $node.Name
        status_code     = [int]$node.statusCode
        status_severity = [string]$node.statusSeverity
        status_message  = [string]$node.statusMessage
        output_file     = $OutputFile
    } | ConvertTo-Json -Depth 4
}
finally {
    if ($sessionOpen -and $null -ne $processor) {
        try { $processor.EndSession($ticket) } catch { Write-Warning $_.Exception.Message }
    }
    if ($connectionOpen -and $null -ne $processor) {
        try { $processor.CloseConnection() } catch { Write-Warning $_.Exception.Message }
    }
    if ($null -ne $auth) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($auth) }
    if ($null -ne $processor) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($processor) }
}
