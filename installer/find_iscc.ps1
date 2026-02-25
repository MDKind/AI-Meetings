$paths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Host "FOUND: $p" }
}

# Registry check
$keys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup_is1",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup_is1"
)
foreach ($k in $keys) {
    $r = Get-ItemProperty $k -ErrorAction SilentlyContinue
    if ($r) { Write-Host "Registry InstallLocation: $($r.InstallLocation)" }
}
