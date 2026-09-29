# Registra una tarea programada de Windows que arranca `python server.py`
# en cada inicio de sesion del usuario actual, corriendo DENTRO de la sesion
# interactiva -- a proposito, no como servicio de Windows: un servicio corre
# en Session 0 sin escritorio ni audio, y Anzo necesita abrir una ventana de
# Chrome real y usar el microfono/parlantes. Ver Anzo/Decisiones.md.
#
# Uso: correr este script una vez (no necesita privilegios de administrador).
# Para desinstalar: scripts\uninstall-autostart.ps1

$ErrorActionPreference = "Stop"

$taskName = "ANZO"
$projectDir = Split-Path -Parent $PSScriptRoot

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Write-Error "No se encontro 'python' en el PATH. Instala Python y confirma que 'python' funciona en una terminal nueva antes de volver a correr este script."
    exit 1
}

$userId = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "server.py" -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Tarea '$taskName' registrada: arranca 'python server.py' en cada inicio de sesion de $userId."
Write-Host "Para probarla ahora mismo sin cerrar sesion: Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Para desinstalarla: scripts\uninstall-autostart.ps1"
