<#
.SYNOPSIS
  Điều phối một spec qua agent thực hiện (codex/gemini/claude) rồi cho Claude review.

.DESCRIPTION
  - Tạo worktree + nhánh riêng `<agent>/<tên-spec>` cạnh repo, không đụng checkout chính.
  - Chạy agent theo mục "Phạm vi agent" của spec: codex (`codex exec`), gemini (`agy -p`), claude (`claude -p`).
  - Kiểm diff: file ngoài "Được sửa" và vượt "Ngân sách diff".
  - Chạy "Lệnh kiểm" của spec ngoài sandbox agent; mã thoát của lệnh là bằng chứng, không phải lời agent.
  - Review hai tầng để tiết kiệm token Claude: Codex (read-only) review trước; chỉ khi Codex ĐẠT thì
    Claude review chốt một lần. Cả hai nhận sẵn diff + kết quả Lệnh kiểm trong prompt, không chạy lại test;
    Claude chỉ có Read/Grep/Glob, model/effort theo dòng "- Review:" của spec (mặc định opus).
    Từ lần review thứ hai, mỗi reviewer chỉ xem phần đổi từ lần review trước của chính nó.
    CẦN SỬA thì đưa phát hiện lại cho agent, tối đa -MaxFixRounds vòng; CHẶN thì dừng.
  - Token/chi phí từng lần review ghi vào usage.tsv trong thư mục log.
  - Frontend (Agent: gemini): -Step mockup cho Gemini dựng mockup trên Penpot qua MCP rồi dừng chờ người duyệt.
    Bước code chỉ chạy khi spec ghi "Mockup: ĐÃ DUYỆT ..." hoặc "Mockup: miễn: <lý do>".
  Script không commit, push, merge, chạy DDL hay chạm dữ liệu thật.
  Mã thoát: 0 ĐẠT, 2 CẦN SỬA/không rõ kết luận, 3 CHẶN.

.EXAMPLE
  .\scripts\agent-run.ps1 -Spec specs\x.md -Step mockup
  .\scripts\agent-run.ps1 -Spec specs\x.md -DryRun
  .\scripts\agent-run.ps1 -Spec specs\x.md
  .\scripts\agent-run.ps1 -Spec specs\x.md -Step check
  .\scripts\agent-run.ps1 -Spec specs\x.md -Step review
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Spec,
    [string]$Branch,
    [string]$Base = 'HEAD',
    [ValidateSet('all', 'mockup', 'run', 'check', 'capture', 'review')][string]$Step = 'all',
    [int]$MaxFixRounds = 2,
    [string]$WorktreeRoot,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $OutputEncoding

$repo = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if (-not $WorktreeRoot) { $WorktreeRoot = Join-Path (Split-Path $repo -Parent) 'worktrees' }

$specFull = (Resolve-Path (Join-Path $repo $Spec) -ErrorAction SilentlyContinue)
if (-not $specFull) { $specFull = Resolve-Path $Spec }
$specFull = $specFull.Path
$specRel = $specFull.Substring($repo.Length + 1) -replace '\\', '/'

# --- Đọc mục "Phạm vi agent" ---------------------------------------------------
$lines = Get-Content -LiteralPath $specFull -Encoding UTF8
$agent = $null; $budget = $null; $mockup = $null; $allowed = @(); $checks = @(); $list = $null
$reviewModel = 'opus'; $reviewEffort = $null
foreach ($l in $lines) {
    if ($l -match '^\s*-\s*Agent:\s*([a-z]+)\s*$') { $agent = $Matches[1]; $list = $null; continue }
    if ($l -match '^\s*-\s*Review:\s*([a-z][a-z0-9.\-]*)(?:\s+(low|medium|high|xhigh|max))?\s*$') {
        $reviewModel = $Matches[1]; $reviewEffort = $Matches[2]; $list = $null; continue
    }
    if ($l -match '^\s*-\s*Mockup:\s*(.+?)\s*$') { $mockup = $Matches[1]; $list = $null; continue }
    if ($l -match '^\s*-\s*Ngân sách diff:\s*(\d+)') { $budget = [int]$Matches[1]; $list = $null; continue }
    if ($l -match '^\s*-\s*Được sửa:') { $list = 'allowed'; continue }
    if ($l -match '^\s*-\s*Lệnh kiểm:') { $list = 'checks'; continue }
    if ($list) {
        if ($l -match '^\s{2,}-\s*`([^`]+)`') {
            if ($list -eq 'allowed') { $allowed += $Matches[1] } else { $checks += $Matches[1] }
            continue
        }
        if ($l.Trim()) { $list = $null }
    }
}
if ($agent -notin @('codex', 'gemini', 'claude')) { throw "Spec thiếu '- Agent: codex|gemini|claude' trong mục Phạm vi agent: $specRel" }
if (-not $allowed) { throw ('Spec thiếu danh sách "- Được sửa:" (mỗi dòng một đường dẫn trong dấu backtick): ' + $specRel) }
if (-not $budget) { $budget = 200 }
$specText = $lines -join "`n"
# Kịch bản chụp giao diện (khối ```json dưới "## Ảnh chụp giao diện"); scripts/ui-capture.js đọc chi tiết.
$capturePage = $null
if ($specText -match '(?m)^## Ảnh chụp giao diện') {
    $capturePage = ([regex]::Match($specText.Substring($specText.IndexOf('## Ảnh chụp giao diện')), '"page"\s*:\s*"([^"]+)"')).Groups[1].Value
    if (-not $capturePage) { throw "Mục '## Ảnh chụp giao diện' của $specRel thiếu ""page"" trong khối json." }
}

$specName = [IO.Path]::GetFileNameWithoutExtension($specFull)
if ($specName -in @('README', '_template')) { $specName = Split-Path (Split-Path $specFull -Parent) -Leaf }
if (-not $Branch) { $Branch = "$agent/$specName" }
$wt = Join-Path $WorktreeRoot ($Branch -replace '[\\/:]', '-')
$logDir = Join-Path $WorktreeRoot ('_logs\' + ($Branch -replace '[\\/:]', '-'))
$baseSha = (git -C $repo rev-parse $Base).Trim()

# Sandbox Windows "elevated" của Codex (cấu hình chung) phải đổi ACL trên node_repl.exe của runtime cua_node
# mỗi lần chạy; file này luôn đang chạy (code-mode host) nên lỗi "setup refresh had errors" (os error 32)
# và mọi lệnh shell bị chặn. "unelevated" vẫn cưỡng chế read-only/workspace-write (kiểm 17/10/2026).
# Giá trị không có dấu ": PowerShell 5.1 làm hỏng " trong đối số native; Codex nhận chuỗi thô khi không phải TOML.
$codexSandbox = @('-c', 'windows.sandbox=unelevated')

# Worktree không có .venv/node_modules/browser: dùng của checkout chính, không tạo junction.
$venvPy = Join-Path $repo '.venv\Scripts\python.exe'
if (Test-Path (Join-Path $repo 'node_modules')) { $env:NODE_PATH = Join-Path $repo 'node_modules' }
if (Test-Path (Join-Path $repo '.playwright-browsers')) { $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $repo '.playwright-browsers' }

Write-Host "Spec      : $specRel"
Write-Host "Agent     : $agent   Ngân sách: $budget dòng   Vòng sửa tối đa: $MaxFixRounds"
Write-Host "Review    : codex (sơ bộ) → claude $reviewModel$(if ($reviewEffort) { " effort $reviewEffort" }) (chốt)"
Write-Host "Được sửa  : $($allowed -join ', ')"
Write-Host "Lệnh kiểm : $(if ($checks) { $checks -join ' | ' } else { '(không có)' })"
if ($agent -eq 'gemini') { Write-Host "Mockup    : $(if ($mockup) { $mockup } else { '(chưa có)' })" }
Write-Host "Chụp UI   : $(if ($capturePage) { $capturePage } else { '(spec không khai báo)' })"
Write-Host "Nhánh     : $Branch  (base $Base = $($baseSha.Substring(0,10)))"
Write-Host "Worktree  : $wt"
Write-Host "Log       : $logDir"
if ($DryRun) { Write-Host "`n-DryRun: dừng trước khi tạo worktree hoặc gọi agent."; return }

New-Item -ItemType Directory -Force $logDir | Out-Null

function Ensure-Worktree {
    if (Test-Path (Join-Path $wt '.git')) { return }
    git -C $repo show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -eq 0) { git -C $repo worktree add $wt $Branch | Out-Host }
    else { git -C $repo worktree add -b $Branch $wt $baseSha | Out-Host }
    if ($LASTEXITCODE -ne 0) { throw 'git worktree add thất bại' }
}

function Assert-Worktree {
    if (-not (Test-Path (Join-Path $wt '.git'))) { throw "Chưa có worktree $wt; chạy -Step run trước." }
}

function Get-ForkPoint { (git -C $wt merge-base HEAD $baseSha).Trim() }

function Get-WorktreeState {
    ((git -C $wt rev-parse HEAD), (git -C $wt status --porcelain), (git -C $wt diff HEAD)) -join "`n"
}

function Read-Log([string]$name) {
    $p = Join-Path $logDir $name
    if (Test-Path $p) { Get-Content -LiteralPath $p -Encoding UTF8 -Raw } else { '' }
}

# Ảnh chụp toàn bộ worktree (cả file chưa track) thành một tree Git qua index tạm;
# không đổi worktree hay index thật. Dùng để chỉ review phần đổi giữa hai lần review.
function Get-Snapshot {
    $idx = Join-Path $logDir 'snapshot.index'
    Remove-Item -LiteralPath $idx -ErrorAction SilentlyContinue
    $env:GIT_INDEX_FILE = $idx
    try {
        git -C $wt read-tree HEAD
        git -C $wt add -A | Out-Null
        $tree = (git -C $wt write-tree).Trim()
    }
    finally { Remove-Item Env:GIT_INDEX_FILE; Remove-Item -LiteralPath $idx -ErrorAction SilentlyContinue }
    if ($LASTEXITCODE -ne 0 -or -not $tree) { throw 'Không chụp được worktree (git write-tree).' }
    $tree
}

# Một dòng/lần gọi reviewer: thời điểm, bước, công cụ, model, token, chi phí (USD, chỉ Claude báo).
function Write-Usage([string]$tag, [string]$tool, [string]$model, $in, $cacheWrite, $cacheRead, $outTok, $cost, $turns) {
    $file = Join-Path $logDir 'usage.tsv'
    if (-not (Test-Path $file)) {
        "time`ttag`ttool`tmodel`tinput`tcache_write`tcache_read`toutput`tcost_usd`tturns" | Set-Content -LiteralPath $file -Encoding UTF8
    }
    ((Get-Date -Format 's'), $tag, $tool, $model, $in, $cacheWrite, $cacheRead, $outTok, $cost, $turns) -join "`t" |
        Add-Content -LiteralPath $file -Encoding UTF8
    Write-Host ("Usage {0} {1}: vào {2} (+ghi cache {3}, đọc cache {4}), ra {5}{6}" -f $tool, $tag, $in, $cacheWrite, $cacheRead, $outTok, $(if ($cost) { ", ~`$$cost" }))
}

# Claude chỉ đọc: Read/Grep/Glob, không Bash/sửa file; model/effort theo spec; trả lời dạng JSON để lấy usage.
function Invoke-ClaudeReviewer([string]$prompt, [string]$out, [string]$tag, [string[]]$extra = @()) {
    $args2 = @('-p', '--model', $reviewModel, '--tools', 'Read,Grep,Glob', '--output-format', 'json', '--no-session-persistence') + $extra
    if ($reviewEffort) { $args2 += @('--effort', $reviewEffort) }
    $before = Get-WorktreeState
    # stderr của CLI (log, cảnh báo) không được thành lỗi dừng script khi đầu ra bị chuyển hướng.
    $ErrorActionPreference = 'Continue'
    Push-Location $wt
    try { $raw = ($prompt | claude @args2) -join "`n"; $code = $LASTEXITCODE }
    finally { Pop-Location; $ErrorActionPreference = 'Stop' }
    if ((Get-WorktreeState) -ne $before) { throw "Claude ($tag) đã làm thay đổi worktree $wt; kiểm git status/diff trước khi dùng kết quả." }
    $j = $null
    try { $j = $raw | ConvertFrom-Json } catch { }
    $text = if ($j) { [string]$j.result } else { $raw }
    $text | Set-Content -LiteralPath $out -Encoding UTF8
    Write-Host $text
    if ($text -match 'hit your session limit|usage limit') { throw "Claude CLI hết giới hạn sử dụng ($($text.Trim())). Chạy lại sau khi reset." }
    if ($code -ne 0 -or -not $j -or $j.is_error -or $text -match 'Not logged in|Please run /login') {
        throw "Claude ($tag) thất bại (mã $code). Đăng nhập CLI bằng 'claude' một lần nếu cần; đầu ra ở $out."
    }
    $u = $j.usage
    Write-Usage $tag 'claude' $reviewModel $u.input_tokens $u.cache_creation_input_tokens $u.cache_read_input_tokens $u.output_tokens ('{0:N3}' -f $j.total_cost_usd) $j.num_turns
    $text
}

# Codex sandbox read-only; --json để lấy usage, -o giữ câu trả lời cuối.
function Invoke-CodexReviewer([string]$prompt, [string]$out, [string]$tag, [string[]]$images = @()) {
    $img = @(); foreach ($p in $images) { $img += @('-i', $p) }
    $before = Get-WorktreeState
    $jsonl = Join-Path $logDir "$tag.jsonl"
    $ErrorActionPreference = 'Continue'
    Push-Location $wt
    try { $prompt | codex exec -C $wt -s read-only @codexSandbox --json -o $out @img -- - | Set-Content -LiteralPath $jsonl -Encoding UTF8; $code = $LASTEXITCODE }
    finally { Pop-Location; $ErrorActionPreference = 'Stop' }
    if ((Get-WorktreeState) -ne $before) { throw "Codex ($tag) đã làm thay đổi worktree $wt; kiểm git status/diff." }
    $text = if (Test-Path $out) { Get-Content -LiteralPath $out -Raw -Encoding UTF8 } else { '' }
    if ($code -ne 0 -or -not $text) { throw "Codex ($tag) thất bại (mã $code); xem $jsonl." }
    Write-Host $text
    $in = 0; $cached = 0; $o = 0
    foreach ($l in (Get-Content -LiteralPath $jsonl -Encoding UTF8)) {
        if ($l -notmatch '"turn.completed"') { continue }
        $u = ($l | ConvertFrom-Json).usage
        $in += [int]$u.input_tokens; $cached += [int]$u.cached_input_tokens; $o += [int]$u.output_tokens
    }
    Write-Usage $tag 'codex' '' $in '' $cached $o '' ''
    $text
}

# --- Ảnh chụp giao diện thật (trước/sau thay đổi) -------------------------------
# Frontend Gemini bắt buộc có kịch bản chụp để reviewer thấy giao diện đã render, không chỉ đọc diff.
function Assert-CaptureSpec {
    if ($agent -eq 'gemini' -and -not $capturePage) {
        throw "Spec frontend (Agent: gemini) thiếu mục '## Ảnh chụp giao diện' với khối json kịch bản chụp. Xem specs/_template.md và docs/multi-agent.md."
    }
}

function Invoke-CaptureTool([string]$root, [string]$out, [string]$label, [string]$compare) {
    $a = @("$repo\scripts\ui-capture.js", '--spec', $specFull, '--root', $root, '--out', $out, '--label', $label)
    if ($compare) { $a += @('--compare', $compare) }
    $ErrorActionPreference = 'Continue'
    try { & node @a | Out-Host; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = 'Stop' }
    if ($code -ne 0) { throw "Chụp giao diện ($label) thất bại (mã $code); sửa khối json trong mục '## Ảnh chụp giao diện' của spec." }
}

# "Trước" chụp từ thư mục trang tại điểm rẽ nhánh (git archive), một lần mỗi lần chạy script.
function Invoke-UiCaptureBefore {
    if (-not $capturePage -or $script:uiBeforeDone) { return }
    $fork = Get-ForkPoint
    $src = Join-Path $logDir 'ui-base-src'
    $zip = Join-Path $logDir 'ui-base-src.zip'
    Remove-Item -LiteralPath $src -Recurse -Force -ErrorAction SilentlyContinue
    git -C $wt archive --format=zip -o $zip $fork -- (Split-Path $capturePage -Parent).Replace('\', '/')
    if ($LASTEXITCODE -ne 0) { throw 'git archive bản trước thay đổi thất bại.' }
    Expand-Archive -LiteralPath $zip -DestinationPath $src -Force
    Remove-Item -LiteralPath $zip
    Invoke-CaptureTool $src (Join-Path $logDir 'ui-before') 'before' ''
    $script:uiBeforeDone = $true
}
$uiBeforeDone = $false

function Invoke-UiCapture {
    if (-not $capturePage) { return }
    Invoke-UiCaptureBefore
    Invoke-CaptureTool $wt (Join-Path $logDir 'ui-after') 'after' (Join-Path $logDir 'ui-before\report.json')
}

# Ảnh board mockup của lần xuất mới nhất (sau khi duyệt không được vẽ đè nên khớp phiên bản đã duyệt).
function Get-MockupExportDir {
    Get-ChildItem -LiteralPath $logDir -Directory -Filter 'mockup-*-export' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^mockup-(\d+)-export$' } | Sort-Object { [int]($_.Name -replace '\D', '') } | Select-Object -Last 1
}

# Ảnh "trước" của các trạng thái đã đạt được trước thay đổi (bỏ trạng thái của thao tác mới).
function Get-BeforeShots {
    $rep = Join-Path $logDir 'ui-before\report.json'
    if (-not (Test-Path $rep)) { return @() }
    @(Get-Content -LiteralPath $rep -Raw -Encoding UTF8 | ConvertFrom-Json | Where-Object { -not $_.stepError } |
        ForEach-Object { Join-Path $logDir "ui-before\$($_.file)" } | Where-Object { Test-Path $_ })
}

# Bằng chứng giao diện cho reviewer: @{Text; Images}. Ảnh theo thứ tự: mockup, sau, trước.
function Get-UiEvidence([switch]$IncludeAfter) {
    $images = @(); $lines = @()
    $mk = Get-MockupExportDir
    if ($agent -eq 'gemini' -and $mockup -match '^miễn') { $lines += "Mockup: miễn ($mockup)." }
    elseif ($mk) {
        foreach ($p in (Get-ChildItem -LiteralPath $mk.FullName -Filter 'board-*.png' | Sort-Object Name)) {
            $images += $p.FullName; $lines += "$($images.Count). MOCKUP $($p.Name) ($($mk.Name)); tên board theo thứ tự trong boards.json"
        }
        $bj = Join-Path $mk.FullName 'boards.json'
        # agy có thể ghi JSON lỗi (ký tự điều khiển trong chuỗi); chỉ lấy tên board cấp cao nhất bằng regex.
        if (Test-Path $bj) {
            $names = [regex]::Matches((Get-Content -LiteralPath $bj -Raw -Encoding UTF8), '(?m)^ {0,4}"name"\s*:\s*"([^"]*)"') | ForEach-Object { $_.Groups[1].Value }
            if ($names) { $lines += 'Tên board theo thứ tự: ' + ($names -join ' | ') }
        }
    }
    elseif ($agent -eq 'gemini') { $lines += 'Không tìm thấy ảnh mockup đã xuất trong log; đối chiếu theo spec.' }
    if ($IncludeAfter) {
        foreach ($p in (Get-ChildItem -LiteralPath (Join-Path $logDir 'ui-after') -Filter '*.png' -ErrorAction SilentlyContinue | Sort-Object Name)) {
            $images += $p.FullName; $lines += "$($images.Count). SAU thay đổi: $($p.Name)"
        }
    }
    foreach ($p in (Get-BeforeShots)) { $images += $p; $lines += "$($images.Count). TRƯỚC thay đổi: $(Split-Path $p -Leaf)" }
    $checks = @()
    if ($IncludeAfter) { $checks += Read-Log 'ui-after\checks.md' } else { $checks += Read-Log 'ui-before\checks.md' }
    @{ Images = $images; Text = (($lines -join "`n") + "`n`nĐo tự động trên giao diện đã render (script chạy; ""MỚI"" = không có trước thay đổi):`n" + ($checks -join "`n")) }
}

function Get-Verdict([string]$text) {
    $m = [regex]::Matches($text, 'Kết luận:\s*\**\s*(ĐẠT|CẦN SỬA|CHẶN)')
    if ($m.Count) { return $m[$m.Count - 1].Groups[1].Value }
    'KHÔNG RÕ'
}

function Invoke-ScopeCheck {
    $fork = Get-ForkPoint
    $changed = @(git -C $wt diff --name-only $fork) + @(git -C $wt ls-files --others --exclude-standard) |
        Where-Object { $_ } | Sort-Object -Unique
    $outside = @($changed | Where-Object { $f = $_; -not ($allowed | Where-Object { $f -like ($_ -replace '\*\*', '*') }) })
    $total = 0
    foreach ($row in (git -C $wt diff --numstat $fork)) {
        $p = $row -split "`t"; if ($p[0] -match '^\d+$') { $total += [int]$p[0] + [int]$p[1] }
    }
    foreach ($u in (git -C $wt ls-files --others --exclude-standard)) {
        $total += @(Get-Content -LiteralPath (Join-Path $wt $u) -ErrorAction SilentlyContinue).Count
    }
    $report = @("File đổi: $($changed.Count); dòng đổi: $total / $budget")
    if ($outside) { $report += 'NGOÀI PHẠM VI:'; $report += $outside | ForEach-Object { "  $_" } }
    if ($total -gt $budget) { $report += "VƯỢT NGÂN SÁCH DIFF: $total > $budget" }
    if (-not $outside -and $total -le $budget) { $report += 'Phạm vi: đạt' }
    $report | Set-Content -LiteralPath (Join-Path $logDir 'scope-check.txt') -Encoding UTF8
    $report | ForEach-Object { Write-Host $_ }
}

# Chạy bằng cmd.exe từ gốc worktree; stdout+stderr vào file để PowerShell 5.1 không biến stderr thành lỗi.
function Invoke-Checks {
    $summary = @()
    $i = 0
    foreach ($c in $checks) {
        $i++
        $cmd = $c.Replace('{python}', "`"$venvPy`"")
        $out = Join-Path $logDir "check-$i.txt"
        Push-Location $wt
        try { & cmd.exe /d /c "$cmd > `"$out`" 2>&1"; $code = $LASTEXITCODE }
        finally { Pop-Location }
        $status = if ($code -eq 0) { 'PASS' } else { "FAIL (mã $code)" }
        $tail = (Get-Content -LiteralPath $out -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 15) -join "`n"
        $summary += "### $c`n$status`n``````n$tail`n``````"
        Write-Host "Kiểm $i`: $status  $c"
    }
    if (-not $checks) { $summary = @('(spec không có Lệnh kiểm)') }
    ($summary -join "`n`n") | Set-Content -LiteralPath (Join-Path $logDir 'checks.md') -Encoding UTF8
}

function Get-TaskPrompt([string]$extra) {
    if ($agent -eq 'gemini') {
        $ux = Get-Content -LiteralPath (Join-Path $repo 'docs\ux-guidelines.md') -Encoding UTF8 -Raw -ErrorAction SilentlyContinue
        $extra = "Code giao diện khớp đúng phiên bản mockup đã duyệt ($mockup) và hướng dẫn UX dưới đây.`nSau khi bạn xong, script chụp giao diện thật theo kịch bản ở mục ""Ảnh chụp giao diện"" của spec (dùng đúng các selector/data-action ghi ở đó) và reviewer so ảnh với mockup; selector trong kịch bản không bấm được thì coi là lỗi.`n===== HƯỚNG DẪN UX =====`n$ux`n$extra"
    }
    @"
Thực hiện spec ``$specRel`` trong thư mục hiện tại (worktree nhánh ``$Branch``).
Đọc AGENTS.md và spec trước khi sửa (spec có thể chưa commit nên được chép nguyên văn ở cuối prompt). Tuân thủ đúng mục "Phạm vi agent":
- Chỉ sửa: $($allowed -join ', ')
- Tổng diff tối đa $budget dòng. Làm cách đơn giản nhất đạt tiêu chí nghiệm thu.
- Không thêm dependency, framework, layer, abstraction, config hay file tiện ích mới ngoài spec. Không refactor/đổi tên/dọn dẹp ngoài yêu cầu.
- Không đổi schema, trường tiền, quyền, quy tắc nghiệp vụ; không chạy DDL/import/deploy; không chạm dữ liệu thật hay captures/.
- Không git commit/push. Không sửa spec. Nếu cần vượt phạm vi: dừng và nêu câu hỏi trong báo cáo cuối.
- Script điều phối sẽ tự chạy các Lệnh kiểm sau khi bạn xong; bạn vẫn nên chạy thử nếu môi trường cho phép. Python: ``$venvPy``.
Cuối cùng báo: file đã sửa, lệnh đã chạy và kết quả, câu hỏi mở.
$extra
===== SPEC $specRel =====
$specText
"@
}

function Invoke-Agent([string]$prompt, [string]$tag) {
    # agy -p tự từ chối mọi lệnh terminal khi không được cấp quyền; không chạy lệnh để khỏi bị dừng giữa chừng.
    if ($agent -eq 'gemini') {
        $prompt += "`nRiêng lượt này: KHÔNG chạy lệnh terminal/shell nào (chế độ headless không được cấp quyền và sẽ dừng phiên). Chỉ đọc và sửa file bằng công cụ file; script điều phối sẽ tự chạy Lệnh kiểm.`n"
    }
    $promptFile = Join-Path $logDir "prompt-$tag.txt"
    $prompt | Set-Content -LiteralPath $promptFile -Encoding UTF8
    $last = Join-Path $logDir "agent-$tag.md"
    Push-Location $wt
    try {
        switch ($agent) {
            'codex' { $prompt | codex exec -C $wt -s workspace-write @codexSandbox -o $last - | Out-Host }
            'claude' { $prompt | claude -p --permission-mode acceptEdits | Tee-Object -FilePath $last | Out-Host }
            # PowerShell 5.1 làm hỏng dấu " trong đối số native, nên agy đọc prompt từ file.
            'gemini' {
                agy -p "Đọc file $promptFile và thực hiện đúng toàn bộ hướng dẫn trong đó." --mode accept-edits --sandbox --add-dir $logDir --print-timeout 20m |
                    Tee-Object -FilePath $last | Out-Host
            }
        }
        $code = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($code -ne 0) { throw "$agent thoát mã $code (xem $last)" }
    if (-not (Test-Path $last) -or -not (Get-Content -LiteralPath $last -Raw -ErrorAction SilentlyContinue)) {
        throw "$agent không trả báo cáo nào (xem log ở trên); có thể bị chặn quyền hoặc hết thời gian."
    }
    Copy-Item -LiteralPath $last -Destination (Join-Path $logDir 'agent-last.md') -Force
}

# Quy trình frontend: mockup Penpot được người dùng duyệt trước khi code (docs/development.md).
function Assert-MockupGate {
    if ($agent -ne 'gemini') { return }
    if ($mockup -match '^miễn:\s*\S') { return }
    # Duyệt phải chỉ vào một phiên bản Penpot cố định, không phải page đang thay đổi.
    if ($mockup -match '^ĐÃ DUYỆT\s+\S+.*phiên bản\s+"[^"]+".*·.+·.+') { return }
    throw "Spec chưa có mockup đã duyệt. Chạy -Step mockup, lưu phiên bản có tên trong Penpot khi duyệt, rồi ghi '- Mockup: ĐÃ DUYỆT <link page> · phiên bản `"<tên version>`" · <người> · <ngày>' (hoặc '- Mockup: miễn: <lý do sửa nhỏ>') vào mục Phạm vi agent."
}

# Bước 1–2 của quy trình frontend phải có trong spec trước khi vẽ.
function Assert-FrontendSpec {
    $missing = @('## Người dùng', '## Đối chiếu dữ liệu') | Where-Object { $specText -notmatch [regex]::Escape($_) }
    if ($missing) { throw "Spec thiếu mục bắt buộc trước mockup: $($missing -join ', '). Xem specs/_template.md và docs/ux-guidelines.md." }
}

# Gọi agy headless trong worktree; prompt đọc từ file (PowerShell 5.1 làm hỏng dấu " trong đối số native).
function Invoke-Agy([string]$promptText, [string]$tag, [string]$timeout = '30m') {
    $promptFile = Join-Path $logDir "prompt-$tag.txt"
    $out = Join-Path $logDir "$tag.md"
    $promptText | Set-Content -LiteralPath $promptFile -Encoding UTF8
    $before = Get-WorktreeState
    Push-Location $wt
    try {
        agy -p "Đọc file $promptFile và thực hiện đúng toàn bộ hướng dẫn trong đó." --mode accept-edits --sandbox --add-dir $logDir --print-timeout $timeout |
            Tee-Object -FilePath $out | Out-Host
    }
    finally { Pop-Location }
    if ((Get-WorktreeState) -ne $before) { throw "agy ($tag) đã làm thay đổi repo trong $wt; kiểm git status/diff." }
    $text = if (Test-Path $out) { Get-Content -LiteralPath $out -Raw -Encoding UTF8 } else { '' }
    if (-not $text) { throw "agy ($tag) không trả kết quả (có thể bị chặn quyền mcp(penpot)/read_url, tab Penpot bị tạm dừng, hoặc hết thời gian)." }
    if ($text -match 'suspended by the browser|no heartbeat|bị tạm dừng') {
        Move-Item -LiteralPath $out -Destination (Join-Path $logDir ("$tag-failed-{0:yyyyMMdd-HHmmss}.md" -f (Get-Date))) -Force
        throw 'Tab Penpot bị trình duyệt tạm dừng. Mở Penpot trong cửa sổ Chrome riêng, đang hiển thị, đã mở đúng file, rồi chạy lại -Step mockup.'
    }
    $text
}

# Kiểm nhanh Penpot trước khi vẽ, để không mất 10–20 phút mới biết tab bị tạm dừng.
function Test-PenpotReady {
    $r = Invoke-Agy 'KHÔNG chạy lệnh terminal. KHÔNG tạo/sửa/xóa gì. Chỉ dùng MCP penpot đọc penpot.currentFile.name. Trả lời đúng một dòng: FILE=<tên file>' 'preflight' '3m'
    if ($r -notmatch 'FILE=\S') { throw "Không đọc được file Penpot đang mở (xem $logDir\preflight.md). Mở đúng file trong Penpot ở cửa sổ Chrome riêng rồi chạy lại." }
    Write-Host "Penpot sẵn sàng: $(([regex]::Match($r, 'FILE=[^\r\n]+')).Value)"
}

function Get-NextMockupIndex {
    $nums = Get-ChildItem -LiteralPath $logDir -Filter 'mockup-*.md' -ErrorAction SilentlyContinue |
        ForEach-Object { if ($_.Name -match '^mockup-(\d+)\.md$') { [int]$Matches[1] } }
    if ($nums) { ($nums | Measure-Object -Maximum).Maximum + 1 } else { 1 }
}

# Trích nội dung và ảnh từng board để kiểm, không tin lời agent tự khai.
function Export-Mockup([int]$n) {
    $dir = Join-Path $logDir "mockup-$n-export"
    New-Item -ItemType Directory -Force $dir | Out-Null
    $null = Invoke-Agy @"
KHÔNG chạy lệnh terminal. KHÔNG tạo/sửa/xóa gì trong Penpot. Trên page ``$specName`` của file Penpot đang mở:
1. Dùng execute_code ĐỌC mọi board cấp cao nhất, tạo chuỗi bằng JSON.stringify (không tự gõ JSON) và ghi nguyên văn chuỗi đó vào file $dir\boards.json dạng:
   [{"name": "...", "x": 0, "y": 0, "width": 0, "height": 0, "texts": [{"text": "...", "fontSize": 14, "inScreen": true}]}]
   inScreen = false nếu text layer là ghi chú cho người duyệt (nằm ngoài vùng khung màn hình hoặc trong board ghi chú), true nếu là chữ người dùng thấy trên màn hình. Sắp text trên xuống, trái sang phải.
2. Với mỗi board, dùng export_shape xuất PNG (scale 1). Ghi file $dir\png-paths.txt: mỗi dòng một đường dẫn tuyệt đối của file PNG vừa xuất, theo thứ tự board (script sẽ tự chép ảnh).
Trả lời ngắn: các file đã ghi.
"@ "mockup-$n-export-run" '15m'
    # agy không ghi được file nhị phân: chép ảnh từ đường dẫn tạm nó báo về.
    $listed = @(Get-ChildItem -LiteralPath $dir -Filter '*.txt' -ErrorAction SilentlyContinue | ForEach-Object {
            [regex]::Matches((Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8), '[A-Za-z]:\\[^\r\n"*?<>|]+?\.png') | ForEach-Object { $_.Value }
        } | Select-Object -Unique)
    $i = 0
    foreach ($src in $listed) {
        if (Test-Path -LiteralPath $src) { $i++; Copy-Item -LiteralPath $src -Destination (Join-Path $dir ('board-{0:D2}.png' -f $i)) -Force }
    }
    $dir
}

# Luật đo được tự động; Claude review phần còn lại.
function Test-MockupRules([string]$dir, [int]$n) {
    $findings = @()
    $jsonPath = Join-Path $dir 'boards.json'
    $boards = $null
    try { $boards = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $findings += "LỖI: không đọc được $jsonPath ($($_.Exception.Message))." }
    foreach ($b in @($boards)) {
        foreach ($t in @($b.texts | Where-Object { $_.inScreen })) {
            $s = "[$($b.name)] ""$($t.text)"""
            if ($t.fontSize -and [double]$t.fontSize -lt 11) { $findings += "LỖI cỡ chữ $($t.fontSize)px < 11px: $s" }
            elseif ($t.fontSize -and [double]$t.fontSize -lt 12) { $findings += "CẢNH BÁO cỡ chữ 11px (chỉ hợp với nhãn trạng thái nhỏ): $s" }
            if ($t.text -match '\d+([.,]\d+)?\s?(tr|triệu|k)\b') { $findings += "LỖI tiền viết tắt: $s" }
            if ($t.text -match '\b(D0\d|Q0\d|S1\d|fixture|RAM|revision|API|guardrail|GUARDRAIL|ids\s*=)') { $findings += "LỖI từ kỹ thuật/mã nội bộ trên màn hình: $s" }
        }
    }
    $pngs = @(Get-ChildItem -LiteralPath $dir -Filter '*.png' -ErrorAction SilentlyContinue)
    if (-not $pngs) { $findings += 'CẢNH BÁO: không có ảnh PNG; review chỉ dựa trên chữ.' }
    if (-not $findings) { $findings = @('Không phát hiện lỗi đo được tự động.') }
    $findings | Set-Content -LiteralPath (Join-Path $logDir "mockup-$n-checks.md") -Encoding UTF8
    $findings | Select-Object -First 15 | ForEach-Object { Write-Host $_ }
}

# Codex xem ảnh (đính kèm) trước; Claude chốt khi Codex ĐẠT, đọc chữ trước và chỉ mở ảnh khi cần.
function Invoke-MockupReview([string]$who, [int]$n, [string]$dir) {
    $ux = Get-Content -LiteralPath (Join-Path $repo 'docs\ux-guidelines.md') -Encoding UTF8 -Raw -ErrorAction SilentlyContinue
    $pngs = @(Get-ChildItem -LiteralPath $dir -Filter '*.png' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $boards = Get-Content -LiteralPath (Join-Path $dir 'boards.json') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($who -eq 'claude') {
        $role = @"
Bạn review CHỐT; Codex đã xem ảnh và kết luận ĐẠT (review của Codex ở cuối). Đọc nội dung chữ trước; chỉ mở ảnh (công cụ Read) để kiểm điều chữ không cho biết (bố cục, cỡ nút, tương phản) hoặc chỗ Codex có thể sót:
$($pngs -join "`n")
"@
    }
    else { $role = 'Bạn review sơ bộ; ảnh từng board đính kèm theo thứ tự board-01, board-02… Claude chỉ review chốt khi bạn ĐẠT.' }
    # Ảnh app hiện tại (trước thay đổi) để kiểm mockup nhất quán với màn hình đang có và đúng tỉ lệ 1:1.
    $current = @(Get-BeforeShots)
    if ($current) {
        $role += "`nSau ảnh board là ảnh GIAO DIỆN HIỆN TẠI của app (chụp thật, trước thay đổi): " + (($current | ForEach-Object { Split-Path $_ -Leaf }) -join ', ') +
            '. Dùng để kiểm mockup giữ đúng tên cột, nút, câu chữ, cỡ chữ và bố cục của màn hình đang có, chỉ khác ở chỗ spec yêu cầu.' +
            $(if ($who -eq 'claude') { "`n" + ($current -join "`n") })
    }
    $prompt = @"
Review mockup Penpot lần $n cho spec ``$specRel`` theo quy trình frontend (docs/development.md) và hướng dẫn UX bên dưới. Người dùng trên 40 tuổi; ưu tiên đúng luồng nghiệp vụ, không thông tin thừa.
$role
Báo cáo của Gemini là lời tự khai, chưa kiểm chứng. Nội dung chữ, kết quả kiểm tự động và báo cáo đã chép sẵn bên dưới; không duyệt toàn repo.
Đối chiếu số liệu, nhãn, câu thông báo với mục "Đối chiếu dữ liệu" của spec; chỉ mở code trong worktree (cong-no-web-handoff/preview) khi cần đối chiếu một điểm cụ thể.
Kiểm: đúng luồng và thứ tự thao tác; mỗi màn hình có thông tin thừa không; dễ đọc với người trên 40 tuổi (cỡ chữ, nút chính, tương phản — nhìn ảnh); ô trống không cộng như 0, khoản chờ không vào tổng nợ; không từ kỹ thuật trên màn hình; chỉ có board màn hình và tối đa một board ghi chú; đủ các trạng thái spec yêu cầu; đúng các lựa chọn đã chốt và góp ý trước.
Không sửa file nào. Báo mỗi phát hiện: board, vấn đề, cần sửa gì (ngắn, cụ thể để Gemini làm theo).
Dòng cuối đúng định dạng: ``Kết luận: ĐẠT`` (sẵn sàng để người dùng duyệt) hoặc ``Kết luận: CẦN SỬA`` hoặc ``Kết luận: CHẶN`` (cần người dùng quyết, ví dụ spec mâu thuẫn hoặc thiếu thông tin nghiệp vụ).

===== HƯỚNG DẪN UX =====
$ux

===== SPEC $specRel =====
$specText

===== KIỂM TỰ ĐỘNG (mockup-$n-checks.md) =====
$(Read-Log "mockup-$n-checks.md")

===== NỘI DUNG CHỮ TỪNG BOARD (boards.json) =====
$boards

===== BÁO CÁO CỦA GEMINI (mockup-$n.md) =====
$(Read-Log "mockup-$n.md")
$(if ($who -eq 'claude') { "`n===== REVIEW SƠ BỘ CỦA CODEX =====`n" + (Read-Log "mockup-$n-review-codex.md") })
"@
    $tag = "mockup-$n-review-$who"
    $out = Join-Path $logDir "$tag.md"
    Write-Host "`n--- $tag ---"
    $text = if ($who -eq 'claude') { Invoke-ClaudeReviewer $prompt $out $tag @('--add-dir', $logDir) } else { Invoke-CodexReviewer $prompt $out $tag ($pngs + $current) }
    Copy-Item -LiteralPath $out -Destination (Join-Path $logDir "mockup-$n-review.md") -Force
    Get-Verdict $text
}

function Invoke-Mockup {
    if ($agent -ne 'gemini') { throw 'Bước mockup chỉ dành cho Agent: gemini.' }
    Assert-FrontendSpec
    if ($mockup -match '^ĐÃ DUYỆT') { throw 'Mockup đã được duyệt theo một phiên bản; không vẽ đè. Muốn chỉnh thì đổi dòng Mockup về CHỜ DUYỆT và ghi lý do vào feedback.md trong thư mục log.' }
    $uxText = Get-Content -LiteralPath (Join-Path $repo 'docs\ux-guidelines.md') -Encoding UTF8 -Raw -ErrorAction SilentlyContinue
    Ensure-Worktree
    Test-PenpotReady
    Invoke-UiCaptureBefore
    # Lịch sử góp ý nằm ở log của nhánh (ngoài repo); spec chỉ giữ điều đã chốt.
    $feedbackFile = Join-Path $logDir 'feedback.md'
    for ($round = 0; ; $round++) {
        $n = Get-NextMockupIndex
        $feedback = if (Test-Path $feedbackFile) { Get-Content -LiteralPath $feedbackFile -Raw -Encoding UTF8 } else { '(chưa có)' }
        $lastReview = Get-ChildItem -LiteralPath $logDir -Filter 'mockup-*-review.md' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
        $reviewText = if ($lastReview) { Get-Content -LiteralPath $lastReview.FullName -Raw -Encoding UTF8 } else { '(chưa có)' }
        $report = Invoke-Agy @"
Bạn phụ trách mockup Penpot cho spec ``$specRel`` (bước 3 của quy trình frontend trong docs/development.md). Lần vẽ thứ $n.
Đọc AGENTS.md, docs/development.md (mục Quy trình frontend), docs/business-rules.md; hướng dẫn UX, góp ý và spec chép nguyên văn ở cuối prompt (có thể chưa commit nên không có trong worktree).
Thứ tự làm: (1) đọc mục "Người dùng và luồng" của spec, vẽ đúng luồng đó theo thứ tự thao tác thật; (2) lấy số liệu, nhãn, câu thông báo từ mục "Đối chiếu dữ liệu" — không bịa; (3) áp dụng hướng dẫn UX: người dùng trên 40 tuổi, chỉ hiện thông tin cần cho quyết định, không có từ kỹ thuật/mã quyết định trên màn hình; (4) nếu đã có mockup trước, chỉ sửa đúng các điểm trong GÓP Ý và REVIEW GẦN NHẤT, giữ phần đã đạt.
$(if (Get-BeforeShots) { "- Ảnh chụp thật của app hiện tại (mở bằng công cụ đọc file nếu xem được ảnh): " + ((Get-BeforeShots) -join '; ') + ". Giữ đúng tên cột, nút, câu chữ, cỡ chữ và tỉ lệ như ảnh; chỉ đổi chỗ spec yêu cầu.`n" })- Dùng MCP server penpot, trên page riêng tên ``$specName`` (dùng lại nếu đã có); không sửa/xóa page hay file khác.
- Page chỉ gồm các board MÀN HÌNH (mỗi board một trạng thái spec yêu cầu, đánh số theo thứ tự thao tác) và đúng MỘT board "Ghi chú" ngắn (tối đa 10 dòng: điểm CÒN MỞ, giả định). Xóa mọi board khác trên page này (ví dụ board ranh giới, lựa chọn đã chốt, gate/tiêu chí) — spec là nguồn duy nhất, không lặp lại spec trong Penpot.
- Khung màn hình chỉ chứa đúng những gì người dùng thấy; không viết ghi chú trong khung.
- Chỉ dữ liệu giả khớp spec; VND nguyên ghi đủ số; ô trống hiện "—" và không cộng như 0; khoản chờ không nằm trong tổng nợ.
- Không tự thêm tính năng, lựa chọn thiết kế hay chính sách ngoài spec.
- KHÔNG sửa file trong repo, KHÔNG chạy lệnh terminal/shell.
- Nếu plugin Penpot báo tab bị trình duyệt tạm dừng: dừng ngay và báo.
Cuối cùng báo ngắn: các board đã có, điểm đã sửa theo góp ý/review, câu hỏi CÒN MỞ. Không tự viết link Penpot nếu không lấy được chính xác từ penpot API.

===== GÓP Ý (feedback.md, người dùng và review trước) =====
$feedback

===== REVIEW GẦN NHẤT CỦA CLAUDE =====
$reviewText

===== HƯỚNG DẪN UX (docs/ux-guidelines.md) =====
$uxText

===== SPEC $specRel =====
$specText
"@ "mockup-$n"
        $dir = Export-Mockup $n
        Test-MockupRules $dir $n
        $verdict = Invoke-MockupReview 'codex' $n $dir
        Write-Host "Codex: $verdict"
        if ($verdict -eq 'ĐẠT') { $verdict = Invoke-MockupReview 'claude' $n $dir; Write-Host "Claude: $verdict" }
        Write-Host "`nMockup lần $n`: $verdict"
        if ($verdict -ne 'CẦN SỬA' -or $round -ge $MaxFixRounds) { break }
    }
    Write-Host "`nKết luận review mockup: $verdict. Báo cáo: $logDir\mockup-$n-review.md; ảnh: $dir"
    if ($verdict -eq 'ĐẠT') {
        Write-Host "Bạn duyệt trên Penpot. Đạt thì lưu phiên bản có tên (History) và ghi vào spec: '- Mockup: ĐÃ DUYỆT <link page> · phiên bản `"<tên>`" · <người> · <ngày>', rồi chạy lại không có -Step."
    }
    Write-Host "Cần chỉnh thì ghi góp ý vào $feedbackFile rồi chạy lại -Step mockup."
}

# $who: codex (sơ bộ) hoặc claude (chốt). $prev: lần review trước của cùng reviewer (@{Tree; File}) để chỉ xem phần đổi.
# Trả @{Verdict; File; Tree}.
function Invoke-Review([string]$who, [string]$tree, $prev, $codexReview) {
    $fork = Get-ForkPoint
    $n = @(Get-ChildItem -LiteralPath $logDir -Filter "review-$who-*.md" -ErrorAction SilentlyContinue).Count
    $tag = "review-$who-$n"
    $out = Join-Path $logDir "$tag.md"
    $stat = (git -C $wt diff --stat $fork $tree) -join "`n"
    if ($prev) {
        $diffTitle = "DIFF TỪ LẦN REVIEW TRƯỚC CỦA BẠN (git diff $($prev.Tree.Substring(0,10)) → hiện tại)"
        $diff = (git -C $wt diff $prev.Tree $tree) -join "`n"
        $mode = @"
Đây là review lại sau vòng sửa. Chỉ kiểm: (a) từng phát hiện trong REVIEW TRƯỚC CỦA BẠN đã được sửa đúng chưa; (b) phần đổi thêm trong diff bên dưới có gây lỗi mới không. Không review lại phần không đổi.
"@
    }
    else {
        $diffTitle = "TOÀN BỘ DIFF (git diff $($fork.Substring(0,10)), gồm cả file chưa track)"
        $diff = (git -C $wt diff $fork $tree) -join "`n"
        $mode = ''
    }
    if ($who -eq 'claude') {
        $role = "Bạn là review CHỐT. Codex đã review sơ bộ và kết luận ĐẠT (xem bên dưới, có thể sót). Tập trung điều Codex dễ bỏ qua: nghiệp vụ/tiền, bất biến trong AGENTS.md, quyền ở backend, test có thật sự chứng minh tiêu chí. Không lặp lại góp ý vặt về style."
    }
    else {
        $role = 'Bạn là review sơ bộ; Claude chỉ review chốt khi bạn kết luận ĐẠT, nên đừng cho ĐẠT nếu còn nghi ngờ thật.'
    }
    $uiSection = ''; $images = @()
    if ($capturePage) {
        $ui = Get-UiEvidence -IncludeAfter
        $images = $ui.Images
        $how = if ($who -eq 'codex') { 'Ảnh đính kèm theo đúng thứ tự danh sách dưới.' }
        else { "Ảnh nằm ở các đường dẫn dưới (thư mục $logDir). Codex đã xem toàn bộ ảnh; bạn đọc phần đo tự động trước, chỉ mở ảnh (Read) cho trạng thái có phát hiện MỚI, chỗ Codex nghi ngờ, hoặc để chốt khớp mockup ở màn hình chính. Không mở ảnh nào thì không khẳng định điều chỉ thấy được trong ảnh; ghi rõ nhận định dựa trên đo tự động hay review của Codex." }
        $uiSection = @"

===== GIAO DIỆN ĐÃ RENDER (script chụp bằng Playwright theo mục "Ảnh chụp giao diện" của spec) =====
$how
Kiểm thêm bằng mắt: (1) mỗi trạng thái SAU khớp board mockup tương ứng (bố cục, thứ tự, nhãn, nút chính, số liệu); (2) so với TRƯỚC, chỉ những chỗ spec yêu cầu bị đổi, không vỡ bố cục/chữ ở phần khác; (3) dễ đọc cho người trên 40 tuổi, không thông tin thừa; (4) mọi LỖI kịch bản hoặc LỖI JS ở bản SAU là lỗi thật (selector trong spec không còn đúng hoặc giao diện hỏng), trừ khi spec nói khác. Phát hiện "có sẵn trước thay đổi" không tính cho lần sửa này, trừ khi spec yêu cầu sửa.
$(($images | ForEach-Object -Begin { $i = 0 } -Process { $i++; if ($who -eq 'claude') { "$i. $_" } }) -join "`n")
$($ui.Text)
"@
    }
    $reviewPrompt = @"
Review thay đổi trong worktree này (nhánh ``$Branch``) so với ``$fork`` theo spec ``$specRel`` và AGENTS.md.
$role
$mode
Diff, kết quả Lệnh kiểm (script đã chạy, là bằng chứng test), spec và báo cáo agent (lời tự khai) đã chép sẵn bên dưới.
KHÔNG chạy lại test, KHÔNG duyệt toàn repo. Chỉ mở file trong worktree khi cần xem ngữ cảnh quanh một chỗ trong diff. Không sửa, tạo, xóa file hay commit.

Ưu tiên theo thứ tự:
1. Sai nghiệp vụ/tiền: VND nguyên, NULL khác 0, cộng lại lịch sử trong opening, phân bổ thu sai, ghi đè posting, thiếu kiểm quyền ở backend.
2. Sai tiêu chí nghiệm thu, Lệnh kiểm FAIL, hoặc thiếu test chứng minh.
3. Over-engineering: abstraction/dependency/config/file mới không cần, sửa ngoài phạm vi, vượt ngân sách diff.
4. Lộ bí mật/dữ liệu khách/ID Sheet/SSH.
Báo mỗi phát hiện: file:dòng, vấn đề, hậu quả cụ thể, đề xuất sửa tối thiểu.
Dòng cuối cùng đúng định dạng: ``Kết luận: ĐẠT`` hoặc ``Kết luận: CẦN SỬA`` hoặc ``Kết luận: CHẶN`` (CHẶN khi cần người quyết, ví dụ phải vượt phạm vi hoặc chạm chính sách tiền).

===== KIỂM PHẠM VI =====
$(Read-Log 'scope-check.txt')

===== LỆNH KIỂM (script chạy) =====
$(Read-Log 'checks.md')

===== SPEC $specRel =====
$specText

===== BÁO CÁO CỦA AGENT (chưa kiểm chứng) =====
$(Read-Log 'agent-last.md')
$(if ($codexReview) { "`n===== REVIEW SƠ BỘ CỦA CODEX =====`n" + (Get-Content -LiteralPath $codexReview.File -Raw -Encoding UTF8) })
$(if ($prev) { "`n===== REVIEW TRƯỚC CỦA BẠN =====`n" + (Get-Content -LiteralPath $prev.File -Raw -Encoding UTF8) })
$uiSection

===== THỐNG KÊ DIFF TOÀN NHÁNH =====
$stat

===== $diffTitle =====
$diff
"@
    Write-Host "`n--- $tag ---"
    $text = if ($who -eq 'claude') { Invoke-ClaudeReviewer $reviewPrompt $out $tag @('--add-dir', $logDir) } else { Invoke-CodexReviewer $reviewPrompt $out $tag $images }
    Copy-Item -LiteralPath $out -Destination (Join-Path $logDir 'review.md') -Force
    @{ Verdict = (Get-Verdict $text); File = $out; Tree = $tree }
}

# Codex review trước; chỉ khi Codex ĐẠT mới tốn một lượt Claude. Trả @{Verdict; File; Tree; Who}.
function Invoke-TwoTierReview {
    $tree = Get-Snapshot
    $script:codexPrev = Invoke-Review 'codex' $tree $script:codexPrev $null
    Write-Host "Codex: $($script:codexPrev.Verdict)"
    if ($script:codexPrev.Verdict -ne 'ĐẠT') { return $script:codexPrev + @{ Who = 'codex' } }
    $script:claudePrev = Invoke-Review 'claude' $tree $script:claudePrev $script:codexPrev
    Write-Host "Claude: $($script:claudePrev.Verdict)"
    $script:claudePrev + @{ Who = 'claude' }
}
$codexPrev = $null; $claudePrev = $null

$verdict = $null
switch ($Step) {
    'mockup' { Invoke-Mockup }
    'run' { Assert-MockupGate; Assert-CaptureSpec; Ensure-Worktree; Invoke-Agent (Get-TaskPrompt '') 'r0'; Invoke-ScopeCheck; Invoke-Checks; Invoke-UiCapture }
    'check' { Assert-Worktree; Invoke-ScopeCheck; Invoke-Checks; Invoke-UiCapture }
    # Thử kịch bản chụp khi viết spec: chụp bản trước (và bản hiện tại của worktree), không gọi agent hay reviewer.
    'capture' {
        if (-not $capturePage) { throw "Spec không có mục '## Ảnh chụp giao diện'." }
        Ensure-Worktree; Invoke-UiCapture
        Write-Host "Ảnh và kết quả đo: $logDir\ui-before, $logDir\ui-after (checks.md, report.json)"
    }
    'review' { Assert-CaptureSpec; Assert-Worktree; Invoke-ScopeCheck; Invoke-Checks; Invoke-UiCapture; $verdict = (Invoke-TwoTierReview).Verdict }
    'all' {
        Assert-MockupGate
        Assert-CaptureSpec
        Ensure-Worktree
        Invoke-Agent (Get-TaskPrompt '') 'r0'
        for ($round = 0; ; $round++) {
            Invoke-ScopeCheck; Invoke-Checks; Invoke-UiCapture
            $r = Invoke-TwoTierReview
            $verdict = $r.Verdict
            Write-Host "`nVòng $round`: $verdict ($($r.Who))"
            if ($verdict -ne 'CẦN SỬA' -or $round -ge $MaxFixRounds) { break }
            $fix = @"

===== VÒNG SỬA $($round + 1): REVIEWER ($($r.Who)) YÊU CẦU SỬA =====
Code hiện tại trong worktree là kết quả vòng trước. Chỉ sửa các phát hiện dưới đây, vẫn trong phạm vi spec.
$(Get-Content -LiteralPath $r.File -Raw -Encoding UTF8)

===== KẾT QUẢ LỆNH KIỂM VÒNG TRƯỚC =====
$(Read-Log 'checks.md')
"@
            Invoke-Agent (Get-TaskPrompt $fix) "r$($round + 1)"
        }
    }
}

Write-Host "`nKhông có gì được commit/push. Log: $logDir; diff: git -C `"$wt`" diff"
if ($verdict) {
    Write-Host "Kết luận cuối: $verdict. Token từng lần review: $logDir\usage.tsv"
    switch ($verdict) { 'ĐẠT' { exit 0 } 'CHẶN' { exit 3 } default { exit 2 } }
}
