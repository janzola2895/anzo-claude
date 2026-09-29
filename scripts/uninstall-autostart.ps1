# Elimina la tarea programada creada por install-autostart.ps1.

$ErrorActionPreference = "Stop"
$taskName = "ANZO"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Tarea '$taskName' eliminada."
} else {
    Write-Host "No hay ninguna tarea '$taskName' registrada."
}
