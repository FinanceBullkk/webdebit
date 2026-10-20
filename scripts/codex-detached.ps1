[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$PromptFile,
    [string]$Worktree = (Get-Location).Path,
    [string]$LogDir,
    [switch]$Worker
)

$ErrorActionPreference = 'Stop'
$PromptFile = [IO.Path]::GetFullPath($PromptFile)
$Worktree = [IO.Path]::GetFullPath($Worktree)
if (-not (Test-Path -LiteralPath $PromptFile -PathType Leaf)) { throw "Prompt file not found: $PromptFile" }
if (-not (Test-Path -LiteralPath $Worktree -PathType Container)) { throw "Worktree not found: $Worktree" }
if (-not $LogDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $LogDir = Join-Path (Split-Path $PromptFile -Parent) "codex-$stamp"
}
$LogDir = [IO.Path]::GetFullPath($LogDir)
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$statusPath = Join-Path $LogDir 'status.json'
$exitPath = Join-Path $LogDir 'exit-code.txt'
$stdoutPath = Join-Path $LogDir 'stdout.log'
$stderrPath = Join-Path $LogDir 'stderr.log'
$reportPath = Join-Path $LogDir 'report.md'
$pidPath = Join-Path $LogDir 'codex.pid'

function Write-Status([string]$State, [Nullable[int]]$ExitCode, [string]$ErrorText) {
    [ordered]@{
        state = $State
        pid = $PID
        prompt_file = $PromptFile
        worktree = $Worktree
        started_at = $script:StartedAt
        finished_at = if ($State -eq 'running') { $null } else { (Get-Date).ToString('o') }
        exit_code = $ExitCode
        error = $ErrorText
    } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

if ($Worker) {
    $script:StartedAt = (Get-Date).ToString('o')
    $PID | Set-Content -LiteralPath $pidPath -Encoding ASCII
    Remove-Item -LiteralPath $exitPath -Force -ErrorAction SilentlyContinue
    Write-Status 'running' $null $null
    $code = 1
    $failure = $null
    try {
        $env:PYTHONUTF8 = '1'
        $env:PYTHONIOENCODING = 'utf-8'
        $node = (Get-Command node.exe -ErrorAction Stop).Source
        $codexJs = Join-Path $env:APPDATA 'npm\node_modules\@openai\codex\bin\codex.js'
        if (-not (Test-Path -LiteralPath $codexJs -PathType Leaf)) { throw "Codex entry point not found: $codexJs" }
        $arguments = @(
            "`"$codexJs`"", 'exec', '-C', "`"$Worktree`"", '-s', 'workspace-write',
            '-c', 'windows.sandbox=unelevated', '-o', "`"$reportPath`"", '-'
        )
        $codex = Start-Process -FilePath $node -ArgumentList $arguments `
            -WorkingDirectory $Worktree -RedirectStandardInput $PromptFile `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath `
            -NoNewWindow -Wait -PassThru
        $code = $codex.ExitCode
    }
    catch {
        $failure = $_.Exception.Message
        $failure | Set-Content -LiteralPath $stderrPath -Encoding UTF8
    }
    finally {
        $code | Set-Content -LiteralPath $exitPath -Encoding ASCII
        Write-Status $(if ($code -eq 0) { 'completed' } else { 'failed' }) $code $failure
    }
    exit $code
}

function Quote-PS([string]$Value) { "'" + $Value.Replace("'", "''") + "'" }
$command = "& $(Quote-PS $PSCommandPath) -PromptFile $(Quote-PS $PromptFile) -Worktree $(Quote-PS $Worktree) -LogDir $(Quote-PS $LogDir) -Worker"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath $pidPath -Encoding ASCII
Write-Output "PID=$($process.Id)"
Write-Output "LOG_DIR=$LogDir"
