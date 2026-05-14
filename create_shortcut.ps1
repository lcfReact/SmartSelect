# SmartSelect - 在桌面创建快捷方式
# 用法：右键 → 用 PowerShell 运行，或在 PowerShell 中执行：
#   powershell -ExecutionPolicy Bypass -File create_shortcut.ps1

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchBat  = Join-Path $ProjectDir "launch.bat"
$IconFile   = Join-Path $ProjectDir "assets\icon.ico"
$Desktop    = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "SmartSelect.lnk"

$WShell = New-Object -ComObject WScript.Shell
$Shortcut = $WShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = $LaunchBat
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description      = "SmartSelect 尾盘选股策略"
$Shortcut.WindowStyle      = 7   # 最小化窗口启动（后台运行）

# 如果有图标文件则使用，否则用 cmd.exe 默认图标
if (Test-Path $IconFile) {
    $Shortcut.IconLocation = $IconFile
} else {
    $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,167"
}

$Shortcut.Save()

Write-Host ""
Write-Host "✅ 快捷方式已创建：$ShortcutPath" -ForegroundColor Green
Write-Host ""
Write-Host "双击桌面「SmartSelect」图标即可启动" -ForegroundColor Cyan
Write-Host ""
