# Crea (o actualiza) la tarea programada de Windows que ejecuta las tiendas solo_local
# (PcComponentes) cada 30 minutos, sin ventana. Ejecutar en PowerShell, sin admin:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1
# Para quitarla: Unregister-ScheduledTask -TaskName bot-precios-local -Confirm:$false
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$uv = (Get-Command uv).Source
$conhost = Join-Path $env:SystemRoot "System32\conhost.exe"

# conhost --headless: la consola existe pero no se muestra ninguna ventana
$accion = New-ScheduledTaskAction -Execute $conhost -WorkingDirectory $repo `
    -Argument "--headless `"$uv`" run --project `"$repo`" python -m bot tarea-local"
$disparo = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)
$ajustes = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
# Batería < 20 % y falta de internet real los comprueba también el propio bot
$usuario = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName "bot-precios-local" -Force `
    -Description "bot-precios: PcComponentes cada 30 min (log en datos\tarea_local.log)" `
    -Action $accion -Trigger $disparo -Settings $ajustes -Principal $usuario | Out-Null
Get-ScheduledTask -TaskName "bot-precios-local" | Select-Object TaskName, State
