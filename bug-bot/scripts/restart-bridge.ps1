# 重启 lark-channel-bridge（Windows 计划任务版），普通权限即可。一般经 bugbot.py restart 调用。
# 原因：bridge 0.7.1 在 Windows 上被 kill / restart 后不清理 registry 里的锁记录，
# 新进程看到旧 PID 就拒绝启动（「当前 profile 已有 bridge 进程占用」/ kill ESRCH）；
# 而 `lark-channel-bridge start` 会重写 launcher.cmd、重新注册任务（需要管理员、会弹黑窗口），所以都不用。
param(
    [string]$Root = (Join-Path $HOME '.lark-channel'),
    [string]$Task = 'LarkChannelBridge.Bot.claude'
)
$ErrorActionPreference = 'Stop'

function Get-RegistryPids {
    $f = Join-Path $Root 'registry\processes.json'
    if (-not (Test-Path $f)) { return @() }
    $j = Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json
    return @($j.entries | ForEach-Object { [int]$_.pid })
}

function Test-TaskRunning {
    $s = cmd /c "schtasks /Query /TN $Task /FO CSV /NH 2>nul"
    return ($s -match '"Running"' -or $s -match '"正在运行"')
}

function Clear-StaleState {
# 清理 PID 已不存在的锁记录和进程登记
Get-ChildItem (Join-Path $Root 'registry\locks') -Recurse -Filter '*.meta.json' -ErrorAction SilentlyContinue | ForEach-Object {
    $meta = Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not (Get-Process -Id ([int]$meta.pid) -ErrorAction SilentlyContinue)) {
        Remove-Item $_.FullName -Force
        Write-Output "清理残留锁 $($_.Name)（PID $($meta.pid) 已退出）"
    }
}
# 强杀后还会残留 proper-lockfile 的互斥标记 <name>.lock.lock（目录），新进程会报
# 「runtime profile lock is already held」。此时已无存活的 bridge 进程，直接删掉。
Get-ChildItem (Join-Path $Root 'registry\locks') -Recurse -Filter '*.lock.lock' -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item $_.FullName -Recurse -Force
    Write-Output "清理残留互斥标记 $($_.Name)"
}
$regFile = Join-Path $Root 'registry\processes.json'
if (Test-Path $regFile) {
    $j = Get-Content $regFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $alive = @($j.entries | Where-Object { Get-Process -Id ([int]$_.pid) -ErrorAction SilentlyContinue })
    $out = [ordered]@{ entries = $alive } | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText($regFile, $out, (New-Object Text.UTF8Encoding $false))
}
}

function Stop-Bridge {
    # 先结束计划任务实例（cmd/conhost 外壳），再杀登记在册的 bridge 进程，等任务真正停下
    cmd /c "schtasks /End /TN $Task >nul 2>nul"
    foreach ($procId in Get-RegistryPids) {
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            Write-Output "停止 bridge 进程 PID $procId"
            Stop-Process -Id $procId -Force
        }
    }
    for ($i = 0; $i -lt 15 -and (Test-TaskRunning); $i++) { Start-Sleep -Seconds 1 }
    Start-Sleep -Seconds 2
}

function Start-AndWait {
    schtasks /Run /TN $Task | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        $pids = Get-RegistryPids
        if ($pids.Count -gt 0 -and (Get-Process -Id $pids[0] -ErrorAction SilentlyContinue)) {
            Write-Host "bridge 已上线，PID $($pids[0])"
            return $true
        }
    }
    return $false
}

for ($attempt = 1; $attempt -le 2; $attempt++) {
    Stop-Bridge
    Clear-StaleState
    if (Start-AndWait) { exit 0 }
    Write-Output "第 $attempt 次启动 60 秒内未上线，重试"
}
Write-Output "启动失败，查看日志：$Root\profiles\claude\logs\daemon\daemon-stderr.log"
exit 1
