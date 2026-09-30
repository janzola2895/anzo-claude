# Crea el acceso directo "ANZO + Claude" en el Escritorio: doble clic y abre la
# ventana de la app (y tu Chrome si estaba cerrado, para la extension).
# Usa pythonw.exe para que no aparezca una consola. Correr una vez.

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Error "No se encontro 'python' en el PATH."; exit 1 }
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Error "No se encontro pythonw.exe junto a python.exe."; exit 1 }

$icon = Join-Path $projectDir "ui\anzo.ico"
if (-not (Test-Path $icon)) { & $python (Join-Path $projectDir "scripts\make_icon.py") }

$lnkPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "ANZO + Claude.lnk"
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $pythonw
$lnk.Arguments = "`"$(Join-Path $projectDir 'Anzo.pyw')`""
$lnk.WorkingDirectory = $projectDir
$lnk.IconLocation = $icon
$lnk.Description = "ANZO + Claude - asistente de voz con tu cuenta de Claude"
$lnk.Save()

Write-Host "Acceso directo creado: $lnkPath"
