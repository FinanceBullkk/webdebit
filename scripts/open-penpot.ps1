<#
.SYNOPSIS
  Mở cửa sổ Chrome riêng cho Penpot để agent vẽ mockup qua Penpot MCP mà tab không bị trình duyệt tạm dừng.

.DESCRIPTION
  Plugin Penpot MCP cần tab Penpot gửi heartbeat liên tục. Chrome mặc định tạm dừng tab khi cửa sổ bị che
  hoặc chạy nền, nên agent hay báo "tab appears to be suspended". Script mở Chrome với hồ sơ riêng
  (không đụng Chrome hằng ngày) và tắt ba cơ chế đó. Lần đầu cần đăng nhập Penpot và mở plugin MCP trong file.

.EXAMPLE
  .\scripts\open-penpot.ps1
  .\scripts\open-penpot.ps1 -Url 'http://localhost:9001/#/workspace?...'
#>
param(
    [string]$Url = 'http://localhost:9001',
    [string]$ProfileDir = (Join-Path $env:LOCALAPPDATA 'penpot-agent-chrome')
)

$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw 'Không tìm thấy chrome.exe.' }

Start-Process -FilePath $chrome -ArgumentList @(
    "--user-data-dir=`"$ProfileDir`"",
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--new-window',
    $Url
)
