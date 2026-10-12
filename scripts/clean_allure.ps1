# 清理 allure 产物（allure-results / allure-report）
#
# 用法（从项目根目录，任意 shell 均可）：
#   powershell -ExecutionPolicy Bypass -File scripts/clean_allure.ps1
#
# 注：这里刻意用 `powershell` 而不是 `pwsh` —— 开发机的 Windows PowerShell 5.1
# 即可运行，不必额外安装 PowerShell 7。脚本本身也兼容 PS7。
#
# 为什么需要专门的脚本：allure-results 每跑一次都会累积 <uuid>-result.json，
# 不清就会把陈旧的执行结果混进新报告里，看到"早就修好的失败"。

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$targets = @("allure-results", "allure-report")

foreach ($name in $targets) {
    $path = Join-Path $root $name
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        Write-Host "[clean_allure] 已删除 $name"
    }
    else {
        Write-Host "[clean_allure] 跳过（不存在）$name"
    }
}
