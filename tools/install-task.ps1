# Dang ky Windows Task Scheduler: cuoi ngay gom usage Claude Code roi push len git.
# Chay: powershell -ExecutionPolicy Bypass -File tools\install-task.ps1 -Machine "PC-Thien"
param(
    [string]$Time = "18:00",       # gio chay hang ngay
    [string]$Machine = "",         # ten may ghi vao cot machine (mac dinh: hostname)
    [string]$Python = "",          # duong dan python.exe neu khong co trong PATH
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "ClaudeUsageDaily"
$repo = Split-Path -Parent $PSScriptRoot

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Da go task $taskName"
    exit 0
}

if (-not $Python) {
    # pythonw khong hien cua so console moi lan chay
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue }
    if (-not $cmd) { throw "Khong thay python trong PATH. Chay lai voi -Python 'C:\...\python.exe'" }
    $Python = $cmd.Source
}
if ($Machine) {
    Set-Content -Path (Join-Path $repo ".machine") -Value $Machine -Encoding utf8 -NoNewline
}

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument ('"{0}"' -f (Join-Path $repo "tools\claude_usage.py")) -WorkingDirectory $repo

# Trigger thu hai: hom truoc may tat thi dang nhap hom sau van chay bu.
$daily = New-ScheduledTaskTrigger -Daily -At $Time
$logon = New-ScheduledTaskTrigger -AtLogOn
$logon.Delay = "PT5M"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $daily, $logon `
    -Settings $settings -Description "Gom usage Claude Code hang ngay va push len git" -Force | Out-Null

Write-Host "Da dang ky task '$taskName'"
Write-Host "  python : $Python"
Write-Host "  repo   : $repo"
Write-Host "  chay   : $Time hang ngay + 5 phut sau moi lan dang nhap"
Write-Host ""
Write-Host "Thu ngay : Start-ScheduledTask -TaskName $taskName"
Write-Host "Xem log  : Get-Content '$repo\.run.log' -Tail 20"
