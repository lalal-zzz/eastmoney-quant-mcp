# install_daily_capture_task.ps1 — 注册晚间采集定时任务 (每日收盘后运行)
#
# 移植自"股票信息"项目 install_eastmoney_rank_tasks.ps1, 目标命令:
#     python -m eastmoney_quant_mcp.cli daily-capture
#
# 用法 (管理员 PowerShell):
#     powershell -ExecutionPolicy Bypass -File scripts\install_daily_capture_task.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\install_daily_capture_task.ps1 `
#         -Python "D:\Anconda\python.exe" -EveningTime "16:30" -DataDir "C:\Users\20127\Desktop"
#
# 数据目录说明: 采集任务本身不联网决定数据位置, 数据根目录由
#     EASTMONEY_DATA_DIR 环境变量 / ~/.eastmoney-quant/config.toml 决定。
#     若提供 -DataDir, 将通过 cmd 包装设置该环境变量后执行 (无需改全局配置)。
# 卸载:
#     Unregister-ScheduledTask -TaskName "EastmoneyQuantDailyCapture" -Confirm:$false

param(
    [string]$Python = "python",
    [string]$DataDir = "",
    [string]$EveningTime = "16:10",
    [string]$TaskName = "EastmoneyQuantDailyCapture"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command $Python -ErrorAction SilentlyContinue) -and -not (Test-Path $Python)) {
    Write-Error "Python 解释器不可用: $Python (可用 -Python 指定完整路径)"
    exit 1
}

# 晚间采集: xuangu 人气排名 + 全市场 spot 快照 + 最近K线增量 + 指标缓存 (自动跳过非交易日)
$moduleArgs = "-m eastmoney_quant_mcp.cli daily-capture --workers 8"

if ($DataDir) {
    $dataFullPath = [System.IO.Path]::GetFullPath($DataDir)
    New-Item -ItemType Directory -Force -Path $dataFullPath | Out-Null
    $execute = "cmd.exe"
    $argument = "/c set `"EASTMONEY_DATA_DIR=$dataFullPath`" && $Python $moduleArgs"
    Write-Host "Data directory: $dataFullPath (per-task env, config.toml 不受影响)"
} else {
    $execute = $Python
    $argument = $moduleArgs
    Write-Host "Data directory: 使用 EASTMONEY_DATA_DIR / config.toml / 默认路径"
}

$action = New-ScheduledTaskAction -Execute $execute -Argument $argument
$trigger = New-ScheduledTaskTrigger -Daily -At $EveningTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Capture Eastmoney popularity rank + full spot + recent klines + indicators after market close (eastmoney-quant-mcp)." `
    -Force | Out-Null

Write-Host "Registered task:"
Write-Host "  $TaskName -> $EveningTime daily, trading days only, rank + spot + kline + indicators"
Write-Host ""
Write-Host "For wake from sleep, also enable Windows wake timers:"
Write-Host "  Control Panel -> Power Options -> Change plan settings -> Advanced -> Sleep -> Allow wake timers -> Enable"
