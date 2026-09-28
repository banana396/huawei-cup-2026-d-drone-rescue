$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$auditPython = (Get-Command python -ErrorAction Stop).Source
& $auditPython (Join-Path $PSScriptRoot 'independent_audit.py')
if ($LASTEXITCODE -ne 0) { throw 'Primary physical check failed. Inspect evidence.' }
& $auditPython (Join-Path $PSScriptRoot 'supplemental_checks.py')
if ($LASTEXITCODE -ne 0) { throw 'Supplemental check failed.' }
& $auditPython (Join-Path $PSScriptRoot 'write_report.py')
if ($LASTEXITCODE -ne 0) { throw 'Report assembly failed.' }
Write-Output 'Audit completed. Read strict_workbook_verdict in 证据/最终验收结论.json; a successful audit run does not mean the workbook passed.'
