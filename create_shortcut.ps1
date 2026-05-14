# SmartSelect - Create desktop shortcut
# Usage: powershell -ExecutionPolicy Bypass -File create_shortcut.ps1

$ProjectDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$LaunchBat    = Join-Path $ProjectDir "launch.bat"
$Desktop      = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "SmartSelect.lnk"

$WShell           = New-Object -ComObject WScript.Shell
$Shortcut         = $WShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = $LaunchBat
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description      = "SmartSelect Stock Selector"
$Shortcut.WindowStyle      = 7
$Shortcut.IconLocation     = "C:\Windows\System32\shell32.dll,167"
$Shortcut.Save()

Write-Host ""
Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "Double-click SmartSelect on your desktop to launch." -ForegroundColor Cyan
Write-Host ""
