<#
.SYNOPSIS
  Ghim agent Zalo (task `ZaloAgent`, máy msi) vào một bản mã bất biến theo SHA của `main`; triển khai và lùi bản là một lệnh.

.DESCRIPTION
  Task chạy `…\cong-no-web-handoff\tools\zalo_agent run …`. Chạy thẳng từ checkout dev thì `git pull`/đổi nhánh ở đó làm agent
  đang chạy nạp lười mã mới lẫn mã cũ (import muộn, `ocr_child.py` và tiến trình WeChat sinh lại), và lượt chạy lại kế tiếp
  chạy nhầm nhánh. Script này dựng `<ReleasesDir>\<sha12>` là một git repo riêng, tách rời checkout dev, checkout đúng SHA
  (không chạm checkout dev ngoài việc `git fetch`), rồi trỏ task sang đó.

  `agent_version` (status.json) vẫn đúng SHA mà KHÔNG sửa mã agent: `status.agent_version` chạy
  `git -C <REPO> rev-parse --short=12 HEAD` với REPO = `parents[3]` của `zalo_agent/__main__.py`, tức gốc repo của bản ghim.

  Lệnh:
    Deploy   [-Sha <sha|ref>]  dựng bản ghim (mặc định `origin/main`), trỏ task sang, khởi động lại, kiểm. Chỉ nhận SHA nằm
                               trong `origin/main` trừ khi có -AllowNonMain.
    Rollback [-Sha <sha>]      về bản trước (theo history.jsonl) hoặc bản -Sha đã dựng; cùng các bước khởi động lại và kiểm.
    Status                     task đang chạy bản nào, tiến trình, status.json, danh sách bản ghim. Không đổi gì.
    Prune                      xóa bản cũ, giữ -Keep bản gần nhất (+ bản đang chạy + bản để lùi).

  Khởi động lại an toàn: đổi Action của task TRƯỚC (tiến trình đang chạy không đổi mã), rồi `Stop-ScheduledTask`; việc này trả về
  khi tiến trình chưa chết, và `Start` ngay sau đó sẽ thấy `agent.lock` còn bị giữ, in "đang có một agent khác chạy" rồi thoát mã 0
  (không agent nào chạy tới lượt lặp 15 phút; gặp 22/11/2026). Nên chờ tới khi không còn tiến trình `zalo_agent … run` của thư mục
  dữ liệu này (quá hạn thì giết) rồi mới `Start`. Tiến trình con mồ côi (`ocr_child.py`, `wechat_export.py`) chỉ được báo, không giết.

  Kiểm sau khởi động: có tiến trình mới chạy từ bản ghim; `<Root>\state\status.json` có `agent_version` = SHA và `at` sau lúc
  khởi động; `hao:/srv/v7/zalo-agent/status.json` cũng vậy (bỏ bằng -SkipHao). Lỗi ở máy thì tự lùi về bản trước (mã thoát 1);
  chỉ hao chưa thấy thì mã thoát 3, không tự lùi.

  Thử không đụng task thật: `-TaskName ZaloAgentTest -ReleasesDir <thư mục thử> -SkipHao`, task thử chạy với `--root` riêng.
  KHÔNG chạy `run --dry-run` trên `D:\zalo-agent` thật (dry-run lưu con trỏ như đã đẩy).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][ValidateSet('Deploy', 'Rollback', 'Status', 'Prune')][string]$Command = 'Status',
    [string]$Sha,
    [string]$TaskName = 'ZaloAgent',
    [string]$ReleasesDir = 'D:\zalo-agent\releases',
    [string]$DevRepo,
    [int]$Keep = 3,
    [string]$HaoStatus = 'hao:/srv/v7/zalo-agent/status.json',
    [switch]$SkipHao,
    [switch]$AllowNonMain,
    [int]$TimeoutSec = 240
)

$ErrorActionPreference = 'Stop'
$DefaultRoot = 'D:\zalo-agent'
$PackageTail = '\cong-no-web-handoff\tools\zalo_agent'
$StatusMaxAgeSec = 120

function Log([string]$Message) { Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message) }

function Invoke-Git {
    # git trả mã khác 0 thì ném; trả về các dòng stdout. stderr của git (tiến độ) không làm lỗi.
    param([string]$Repo, [string[]]$GitArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & git -C $Repo @GitArgs 2>$null } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') lỗi (mã $LASTEXITCODE) ở $Repo" }
    return $out
}

function Get-RepoHead([string]$Repo) {
    try { return ([string](Invoke-Git $Repo @('rev-parse', 'HEAD'))).Trim() } catch { return $null }
}

function Get-TaskInfo {
    # Đọc Action của task: python, tham số, thư mục làm việc, gốc repo của bản đang chạy, gốc dữ liệu (--root).
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $action = $task.Actions | Select-Object -First 1
    $m = [regex]::Match([string]$action.Arguments, '"([^"]*)' + [regex]::Escape($PackageTail) + '"')
    if (-not $m.Success) { throw "Action của task $TaskName không có đường dẫn `"…$PackageTail`": $($action.Arguments)" }
    $rootMatch = [regex]::Match([string]$action.Arguments, '--root\s+(?:"([^"]+)"|(\S+))')
    $root = $DefaultRoot
    if ($rootMatch.Success) { $root = if ($rootMatch.Groups[1].Success) { $rootMatch.Groups[1].Value } else { $rootMatch.Groups[2].Value } }
    [pscustomobject]@{
        Task = $task; Execute = [string]$action.Execute; Arguments = [string]$action.Arguments
        WorkingDirectory = [string]$action.WorkingDirectory; RepoPath = $m.Groups[1].Value; Root = $root.TrimEnd('\')
    }
}

function Get-AgentProcess([string]$Root) {
    # Tiến trình agent `zalo_agent … run` của đúng thư mục dữ liệu $Root (task thử không bị tiến trình thật chặn).
    $found = @()
    foreach ($p in (Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'")) {
        $c = [string]$p.CommandLine
        if (-not $c -or $c -notmatch 'zalo_agent"?\s+run(\s|$)') { continue }
        $r = $DefaultRoot
        $rm = [regex]::Match($c, '--root\s+(?:"([^"]+)"|(\S+))')
        if ($rm.Success) { $r = if ($rm.Groups[1].Success) { $rm.Groups[1].Value } else { $rm.Groups[2].Value } }
        if ($r.TrimEnd('\') -ieq $Root) { $found += $p }
    }
    return $found
}

function Get-OrphanChild([string]$RepoPath) {
    # `ocr_child.py` / `wechat_export.py` còn sống sau khi agent chết (chỉ báo, không giết).
    $pattern = [regex]::Escape($RepoPath + $PackageTail) + '[\\/](ocr_child|wechat_export)\.py'
    return @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern })
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}

function Read-AgentStatus([string]$Root) { Read-JsonFile (Join-Path $Root 'state\status.json') }

function Read-HaoStatus {
    if ($SkipHao) { return $null }
    $m = [regex]::Match($HaoStatus, '^([A-Za-z0-9._-]+):(/[A-Za-z0-9._/-]+)$')
    if (-not $m.Success) { throw "-HaoStatus phải có dạng host:/đường/dẫn, nhận được: $HaoStatus" }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $text = & ssh -o BatchMode=yes -o ConnectTimeout=20 $m.Groups[1].Value "cat $($m.Groups[2].Value)" 2>$null } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0 -or -not $text) { return $null }
    try { return ($text -join "`n") | ConvertFrom-Json } catch { return $null }
}

function Test-StatusFresh($Status, [string]$Short, [datetime]$Since) {
    # status.json do bản $Short ghi SAU lúc $Since (loại status cũ của bản trước).
    if (-not $Status -or -not $Status.agent_version -or -not $Status.at) { return $false }
    if (-not ([string]$Status.agent_version).StartsWith($Short) -and -not $Short.StartsWith([string]$Status.agent_version)) { return $false }
    try { $at = [datetimeoffset]::Parse([string]$Status.at).UtcDateTime } catch { return $false }
    return $at -ge $Since.ToUniversalTime()
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds, [int]$StepSec = 2) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds $StepSec
    }
    return [bool](& $Condition)
}

function Resolve-DevRepo {
    if ($DevRepo) { return (Resolve-Path -LiteralPath $DevRepo).Path }
    $top = ([string](Invoke-Git $PSScriptRoot @('rev-parse', '--show-toplevel'))).Trim()
    return (Resolve-Path -LiteralPath $top).Path
}

function Resolve-Release {
    # Tên thư mục bản ghim: 12 ký tự đầu của SHA đầy đủ.
    param([string]$Repo, [string]$Ref)
    $full = ([string](Invoke-Git $Repo @('rev-parse', '--verify', '--quiet', "$Ref^{commit}"))).Trim()
    if ($full -notmatch '^[0-9a-f]{40}$') { throw "Không phân giải được $Ref thành SHA" }
    return $full
}

function Build-Release([string]$Repo, [string]$Full) {
    # Dựng $ReleasesDir\<sha12> từ mã của $Repo ở đúng $Full: git repo riêng (không dùng chung object, không worktree).
    $short = $Full.Substring(0, 12)
    $final = Join-Path $ReleasesDir $short
    if ((Test-Path -LiteralPath $final) -and ((Get-RepoHead $final) -eq $Full)) {
        $dirty = @(Invoke-Git $final @('status', '--porcelain'))
        if ($dirty.Count -eq 0) { Log "Bản $short đã dựng và sạch, dùng lại."; return $final }
        Log "Bản $short có $($dirty.Count) thay đổi lạ (bản ghim phải bất biến); dựng lại."
    }
    New-Item -ItemType Directory -Force -Path $ReleasesDir | Out-Null
    $tmp = Join-Path $ReleasesDir "$short.tmp-$PID"
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    Log "Dựng bản $short từ $Repo ..."
    try {
        New-Item -ItemType Directory -Path $tmp | Out-Null
        Invoke-Git $tmp @('init', '--quiet') | Out-Null
        Invoke-Git $tmp @('config', 'gc.auto', '0') | Out-Null
        Invoke-Git $tmp @('config', 'core.autocrlf', 'false') | Out-Null
        Invoke-Git $tmp @('fetch', '--quiet', '--no-tags', '--depth', '1', $Repo, $Full) | Out-Null
        Invoke-Git $tmp @('checkout', '--quiet', '--detach', 'FETCH_HEAD') | Out-Null
        if ((Get-RepoHead $tmp) -ne $Full) { throw "Bản dựng ở $tmp không ở đúng $Full" }
        if (Test-Path -LiteralPath $final) { Remove-Item -LiteralPath $final -Recurse -Force }
        Move-Item -LiteralPath $tmp -Destination $final
    } catch {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
        throw
    }
    return $final
}

function Test-ReleaseImports([string]$Release, [string]$PythonExe) {
    # `run --help` nạp mọi module mức đầu của gói: bắt thiếu tệp/lỗi cú pháp trước khi đụng task.
    $python = Join-Path (Split-Path $PythonExe) 'python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = $PythonExe }
    $package = Join-Path $Release ($PackageTail.TrimStart('\'))
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & $python -X utf8 -I $package run --help 2>&1 } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "Bản ghim không nạp được (python -I $package run --help, mã $LASTEXITCODE): $(($out | Select-Object -First 3) -join ' | ')" }
}

function Get-ActionlessXml([string]$Name) {
    # Toàn bộ định nghĩa task trừ Actions và ngày đăng ký: để chứng minh trigger, cài đặt pin, principal không đổi.
    $xml = [xml](Export-ScheduledTask -TaskName $Name)
    foreach ($node in @($xml.Task.Actions)) { if ($node) { [void]$node.ParentNode.RemoveChild($node) } }
    $date = $xml.Task.RegistrationInfo.SelectSingleNode("*[local-name()='Date']")
    if ($date) { [void]$date.ParentNode.RemoveChild($date) }
    return $xml.OuterXml
}

function Set-TaskRelease($Info, [string]$Release) {
    # Trỏ Action sang $Release, giữ nguyên Python, mọi tham số, trigger, cài đặt. Kiểm phần còn lại của task không đổi.
    $newPackage = Join-Path $Release ($PackageTail.TrimStart('\'))
    $oldPackage = $Info.RepoPath + $PackageTail
    $newArgs = $Info.Arguments.Replace('"' + $oldPackage + '"', '"' + $newPackage + '"')
    if ($newArgs -eq $Info.Arguments -and $Info.RepoPath -ne $Release) { throw "Không thay được đường dẫn gói trong tham số: $($Info.Arguments)" }
    $beforeXml = Export-ScheduledTask -TaskName $TaskName
    $beforeRest = Get-ActionlessXml $TaskName
    $backup = Join-Path $ReleasesDir ("task-{0}-{1}.xml" -f $TaskName, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $ReleasesDir | Out-Null
    Set-Content -LiteralPath $backup -Value $beforeXml -Encoding Unicode
    $action = New-ScheduledTaskAction -Execute $Info.Execute -Argument $newArgs -WorkingDirectory $Release
    Set-ScheduledTask -TaskName $TaskName -Action $action | Out-Null
    $afterRest = Get-ActionlessXml $TaskName
    if ($afterRest -ne $beforeRest) {
        Log "Phần ngoài Action của task đổi sau Set-ScheduledTask: khôi phục từ $backup"
        Register-ScheduledTask -TaskName $TaskName -Xml $beforeXml -Force | Out-Null
        throw "Set-ScheduledTask làm đổi trigger/cài đặt/principal của $TaskName; đã khôi phục bản XML cũ ($backup)."
    }
    Log "Task $TaskName trỏ sang $Release (XML cũ lưu ở $backup)."
}

function Restart-Agent([string]$Root, [string]$OldRepoPath) {
    # Chờ tiến trình cũ chết hẳn rồi mới Start (bẫy agent.lock). Trả về lúc bấm Start.
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $gone = Wait-Until { @(Get-AgentProcess $Root).Count -eq 0 } 30
    if (-not $gone) {
        $left = @(Get-AgentProcess $Root)
        Log "Sau 30 giây còn $($left.Count) tiến trình agent; giết (khóa agent.lock tự nhả khi tiến trình chết)."
        foreach ($p in $left) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        $gone = Wait-Until { @(Get-AgentProcess $Root).Count -eq 0 } 30
    }
    if (-not $gone) { throw "Còn tiến trình agent của $Root sau khi giết; không Start (sẽ gặp 'đang có một agent khác chạy')." }
    $idle = Wait-Until { (Get-ScheduledTask -TaskName $TaskName).State -ne 'Running' } 30
    if (-not $idle) { throw "Task $TaskName vẫn ở trạng thái Running dù không còn tiến trình." }
    $orphans = Get-OrphanChild $OldRepoPath
    if ($orphans.Count -gt 0) { Log "Còn $($orphans.Count) tiến trình con mồ côi (ocr_child/wechat_export); không giết, bản cũ chưa dọn được tới khi chúng thoát." }
    $started = Get-Date
    Start-ScheduledTask -TaskName $TaskName
    Log "Đã Start $TaskName."
    return $started
}

function Confirm-Running([string]$Release, [string]$Root, [datetime]$Started, [string]$Full) {
    # Kiểm ở máy: tiến trình chạy từ bản ghim, status.json đúng SHA và mới. Trả về $true/$false.
    $short = $Full.Substring(0, 12)
    $needle = $Release + $PackageTail
    $up = Wait-Until { @(Get-AgentProcess $Root | Where-Object { $_.CommandLine.Contains($needle) }).Count -ge 1 } 30
    if (-not $up) { Log "KHÔNG thấy tiến trình agent chạy từ $needle."; return $false }
    $fresh = Wait-Until { Test-StatusFresh (Read-AgentStatus $Root) $short $Started } $TimeoutSec 3
    $status = Read-AgentStatus $Root
    if (-not $fresh) { Log "status.json ở máy chưa có agent_version=$short mới sau $TimeoutSec giây (đang: $($status.agent_version), at $($status.at))."; return $false }
    Log "Máy: agent_version=$short, status.json lúc $($status.at), identity=$($status.identity)."
    return $true
}

function Write-History([hashtable]$Entry) {
    New-Item -ItemType Directory -Force -Path $ReleasesDir | Out-Null
    $Entry['at'] = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    $Entry['task'] = $TaskName
    Add-Content -LiteralPath (Join-Path $ReleasesDir 'history.jsonl') -Value ($Entry | ConvertTo-Json -Compress) -Encoding UTF8
}

function Get-History {
    $path = Join-Path $ReleasesDir 'history.jsonl'
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    return @(Get-Content -LiteralPath $path -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.task -eq $TaskName })
}

function Get-PreviousRelease([string]$CurrentPath) {
    # Bản trước = `from` của lần chuyển gần nhất vào $CurrentPath còn tồn tại trên đĩa.
    $items = @(Get-History)
    [array]::Reverse($items)
    foreach ($h in $items) {
        if ($h.to_path -ieq $CurrentPath -and $h.from_path -and ($h.from_path -ine $CurrentPath) -and (Test-Path -LiteralPath $h.from_path)) { return [string]$h.from_path }
    }
    return $null
}

function Invoke-Prune([string]$CurrentPath, [string]$PreviousPath) {
    if (-not (Test-Path -LiteralPath $ReleasesDir)) { return }
    $dirs = @(Get-ChildItem -LiteralPath $ReleasesDir -Directory | Where-Object { $_.Name -match '^[0-9a-f]{12}$' } | Sort-Object LastWriteTime -Descending)
    $keepNames = @($dirs | Select-Object -First $Keep | ForEach-Object { $_.FullName })
    foreach ($d in $dirs) {
        if ($keepNames -contains $d.FullName -or $d.FullName -ieq $CurrentPath -or ($PreviousPath -and $d.FullName -ieq $PreviousPath)) { continue }
        try { Remove-Item -LiteralPath $d.FullName -Recurse -Force; Log "Đã xóa bản cũ $($d.Name)." }
        catch { Log "Không xóa được $($d.Name) (còn tiến trình giữ file?): $($_.Exception.Message)" }
    }
    Get-ChildItem -LiteralPath $ReleasesDir -Directory | Where-Object { $_.Name -match '\.tmp-\d+$' -and $_.LastWriteTime -lt (Get-Date).AddDays(-1) } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

function Switch-Release([string]$Release, [string]$Action) {
    # Trỏ task sang $Release, khởi động lại, kiểm máy rồi hao. Máy lỗi thì lùi (trừ khi đang lùi). Trả về mã thoát.
    $info = Get-TaskInfo
    $full = Get-RepoHead $Release
    if (-not $full) { throw "$Release không phải git repo hoặc không có HEAD" }
    $short = $full.Substring(0, 12)
    $fromPath = $info.RepoPath
    if ($fromPath -ieq $Release) { Log "Task $TaskName đã trỏ vào $Release; khởi động lại để chắc chắn." }
    Test-ReleaseImports $Release $info.Execute
    # Dấu "mới dùng" cho Prune; không bắt buộc (thư mục đang là cwd của tiến trình thì Windows từ chối đổi giờ).
    try { (Get-Item -LiteralPath $Release).LastWriteTime = Get-Date } catch { Log "Không cập nhật giờ của $Release (đang được dùng); bỏ qua." }
    Set-TaskRelease $info $Release
    Write-History @{ action = $Action; from_path = $fromPath; to_path = $Release; to_sha = $full }
    $info2 = Get-TaskInfo
    $started = Restart-Agent $info2.Root $fromPath
    $local = Confirm-Running $Release $info2.Root $started $full
    if (-not $local) {
        if ($Action -ne 'rollback' -and $fromPath -and (Test-Path -LiteralPath $fromPath) -and ($fromPath -ine $Release)) {
            Log "Kiểm ở máy hỏng: lùi về $fromPath."
            [void](Switch-Release $fromPath 'rollback')
        }
        return 1
    }
    if ($SkipHao) { Log 'Bỏ qua kiểm hao (-SkipHao).'; return 0 }
    $haoOk = Wait-Until { Test-StatusFresh (Read-HaoStatus) $short $started } $TimeoutSec 5
    $hao = Read-HaoStatus
    if (-not $haoOk) { Log "hao CHƯA thấy agent_version=$short mới (đang: $($hao.agent_version), at $($hao.at)); máy đã chạy bản mới, kiểm mạng/ssh rồi chạy Status."; return 3 }
    Log "hao: agent_version=$short, status.json lúc $($hao.at)."
    return 0
}

function Show-Status {
    $info = Get-TaskInfo
    $current = Get-RepoHead $info.RepoPath
    $under = $info.RepoPath.StartsWith($ReleasesDir, [StringComparison]::OrdinalIgnoreCase)
    Log ("Task {0}: trạng thái {1}, chạy từ {2} ({3})" -f $TaskName, $info.Task.State, $info.RepoPath, $(if ($under) { 'bản ghim' } else { 'KHÔNG phải bản ghim: checkout dev' }))
    Log ("Bản đang trỏ: {0}; thư mục làm việc: {1}" -f $(if ($current) { $current.Substring(0, 12) } else { 'không đọc được' }), $info.WorkingDirectory)
    $procs = @(Get-AgentProcess $info.Root)
    Log "Tiến trình agent (root $($info.Root)): $($procs.Count)$(if ($procs.Count) { ' - pid ' + (($procs | ForEach-Object ProcessId) -join ',') })"
    $status = Read-AgentStatus $info.Root
    if ($status) { Log "status.json ở máy: agent_version=$($status.agent_version), at $($status.at)" } else { Log 'status.json ở máy: chưa có' }
    if ($status -and $current -and -not $current.StartsWith([string]$status.agent_version)) {
        Log "LƯU Ý: mã ở đường dẫn của task ($($current.Substring(0, 12))) khác bản agent đang chạy ($($status.agent_version)); lệch này là rủi ro của chạy thẳng từ checkout dev."
    }
    if (-not $SkipHao) {
        $hao = Read-HaoStatus
        if ($hao) { Log "status.json trên hao: agent_version=$($hao.agent_version), at $($hao.at)" } else { Log 'status.json trên hao: không đọc được' }
    }
    $prev = Get-PreviousRelease $info.RepoPath
    Log "Bản để lùi: $(if ($prev) { $prev } else { 'không có' })"
    if (Test-Path -LiteralPath $ReleasesDir) {
        Get-ChildItem -LiteralPath $ReleasesDir -Directory | Where-Object { $_.Name -match '^[0-9a-f]{12}$' } | Sort-Object LastWriteTime -Descending |
            ForEach-Object { Log ("  {0}  {1}{2}" -f $_.Name, $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm'), $(if ($_.FullName -ieq $info.RepoPath) { '  <- đang chạy' } else { '' })) }
    }
}

# ---- chạy ----
switch ($Command) {
    'Status' { Show-Status; exit 0 }
    'Prune' {
        $info = Get-TaskInfo
        Invoke-Prune $info.RepoPath (Get-PreviousRelease $info.RepoPath)
        exit 0
    }
    'Deploy' {
        $repo = Resolve-DevRepo
        $ref = if ($Sha) { $Sha } else { 'origin/main' }
        if (-not $Sha -or $Sha -notmatch '^[0-9a-f]{40}$') {
            Log 'git fetch origin main (chỉ cập nhật origin/main, không đổi nhánh hay cây làm việc).'
            Invoke-Git $repo @('fetch', '--quiet', 'origin', 'main') | Out-Null
        }
        $full = Resolve-Release $repo $ref
        if (-not $AllowNonMain) {
            $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            & git -C $repo merge-base --is-ancestor $full origin/main 2>$null
            $isMain = ($LASTEXITCODE -eq 0)
            $ErrorActionPreference = $previous
            if (-not $isMain) { throw "SHA $($full.Substring(0, 12)) không nằm trong origin/main (thêm -AllowNonMain nếu chủ ý)." }
        }
        $release = Build-Release $repo $full
        $code = Switch-Release $release 'deploy'
        $info = Get-TaskInfo
        Invoke-Prune $info.RepoPath (Get-PreviousRelease $info.RepoPath)
        if ($code -eq 0) { Log "Xong: $($full.Substring(0, 12)). Lùi: powershell -File $PSCommandPath Rollback" }
        elseif ($code -eq 3) { Log "Máy chạy $($full.Substring(0, 12)) nhưng hao chưa thấy (mã 3). Lùi: powershell -File $PSCommandPath Rollback" }
        else { Log "KHÔNG xong (mã $code): task đang chạy $((Get-TaskInfo).RepoPath); xem các dòng trên." }
        exit $code
    }
    'Rollback' {
        $info = Get-TaskInfo
        if ($Sha) {
            $target = Join-Path $ReleasesDir $Sha.Substring(0, [Math]::Min(12, $Sha.Length))
        } else {
            $target = Get-PreviousRelease $info.RepoPath
            if (-not $target) { throw 'Không có bản trước trong history.jsonl để lùi; dùng -Sha <sha> của bản đã dựng.' }
        }
        if (-not (Test-Path -LiteralPath $target)) { throw "Không có bản $target" }
        $code = Switch-Release $target 'rollback'
        Log "Đã lùi về $target."
        exit $code
    }
}
