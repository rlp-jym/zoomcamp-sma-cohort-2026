$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$task = "IndexBreadthDailySignal"

$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$here\breadth_signal_send.bat`" scheduled" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 3:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger `
    -Settings $settings -Description "Index breadth momentum daily signal" -Force | Out-Null

Write-Host "Registered $task for 03:00, Monday to Friday."
Write-Host "Test now : schtasks /Run /TN `"$task`""
Write-Host "Remove   : schtasks /Delete /TN `"$task`" /F"
