<#
.SYNOPSIS
    Регистрирует контент-завод в Планировщике заданий Windows.

.DESCRIPTION
    Создаёт задачу ContentFactory, которая:
      - запускается при входе пользователя в систему (или при старте Windows
        с ключом -AtStartup, нужны права администратора);
      - затем каждые N минут выполняет одну проверку расписания:
        python -m content_factory daemon --once.

    Такой режим безопасен: каждый запуск — отдельный короткий процесс,
    второй экземпляр не стартует (MultipleInstances = IgnoreNew).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-task.ps1

.EXAMPLE
    # Проверка каждые 5 минут, своё имя задачи
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-task.ps1 -IntervalMinutes 5 -TaskName ContentFactory

.EXAMPLE
    # Запуск при старте Windows (только из PowerShell от администратора)
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-task.ps1 -AtStartup

.NOTES
    Удалить задачу:
        Unregister-ScheduledTask -TaskName ContentFactory -Confirm:$false
#>
[CmdletBinding()]
param(
    [string]$TaskName = "ContentFactory",
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 10,
    [string]$ProjectRoot = "",
    [switch]$AtStartup,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object -TypeName Security.Principal.WindowsPrincipal -ArgumentList $identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- Определяем корень проекта --------------------------------------
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

$RunBat = Join-Path $ProjectRoot "scripts\windows\run.bat"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EnvFile = Join-Path $ProjectRoot ".env"

Write-Host "===================================================================="
Write-Host " Контент-завод: регистрация в Планировщике заданий"
Write-Host "===================================================================="
Write-Host " Задача:        $TaskName"
Write-Host " Проект:        $ProjectRoot"
Write-Host " Интервал:      каждые $IntervalMinutes мин (daemon --once)"
Write-Host " Триггер:       $(if ($AtStartup) { 'при старте Windows' } else { 'при входе пользователя' })"

# --- Удаление задачи --------------------------------------------------
if ($Uninstall) {
    Write-Step "Удаляю задачу $TaskName"
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "Задача $TaskName не найдена — нечего удалять." -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Задача $TaskName удалена." -ForegroundColor Green
    exit 0
}

# --- Проверки ---------------------------------------------------------
Write-Step "Проверяю окружение"
if (-not (Test-Path $RunBat)) {
    throw "Не найден $RunBat. Запустите скрипт из папки проекта content-factory."
}
if (-not (Test-Path $PythonExe)) {
    throw "Не найдено виртуальное окружение: $PythonExe. Сначала выполните установку (python -m venv .venv; pip install -r requirements.txt)."
}
if (-not (Test-Path $EnvFile)) {
    Write-Host "ВНИМАНИЕ: не найден .env. Скопируйте .env.example в .env и заполните токены." -ForegroundColor Yellow
    Write-Host "        Без токенов программа будет работать в dry-run (посты в data\outbox)."
}
if ($AtStartup -and -not (Test-IsAdmin)) {
    throw "Ключ -AtStartup требует прав администратора. Запустите PowerShell от имени администратора или уберите -AtStartup."
}

$logsDir = Join-Path $ProjectRoot "data\logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

# --- Действие: cmd.exe /c "...\run.bat" --once ------------------------
Write-Step "Создаю действие задачи"
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument ('/c ""{0}" --once"' -f $RunBat) `
    -WorkingDirectory $ProjectRoot
Write-Host " Действие: $($action.Execute) $($action.Arguments)"

# --- Триггеры ---------------------------------------------------------
Write-Step "Создаю триггеры"
if ($AtStartup) {
    $initialTrigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $initialTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
}

# Периодический запуск: первая проверка через минуту, затем каждые N минут.
$periodicTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$triggers = @($initialTrigger, $periodicTrigger)

# --- Параметры задачи -------------------------------------------------
Write-Step "Настраиваю параметры"
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

if ($AtStartup) {
    # При старте Windows задача выполняется от SYSTEM (нужны права админа).
    # Это надёжно для сервера/мини-ПК, который работает без входа в систему.
    $principal = New-ScheduledTaskPrincipal `
        -UserId "SYSTEM" `
        -LogonType ServiceAccount `
        -RunLevel Highest
} else {
    # Обычный режим: задача работает от текущего пользователя, пока он в системе.
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
}

# --- Регистрация ------------------------------------------------------
Write-Step "Регистрирую задачу $TaskName"
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description "Контент-завод: сбор новостей и публикация в Telegram-каналы (daemon --once каждые $IntervalMinutes мин)." `
    -Force | Out-Null

Write-Step "Запускаю задачу один раз для проверки"
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host ""
Write-Host "Задача зарегистрирована." -ForegroundColor Green
Write-Host "  Состояние:   $($task.State)"
Write-Host "  Последний запуск: $($info.LastRunTime)"
Write-Host "  Результат:   $($info.LastTaskResult)"
Write-Host ""
Write-Host "Полезные команды:"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Stop-ScheduledTask  -TaskName $TaskName"
Write-Host "  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "Логи программы: $logsDir\factory.log" -ForegroundColor Cyan
Write-Host "Демо и проверка: python -m content_factory demo; python -m content_factory sources check"
Write-Host ""
Write-Host "Чтобы публикация была реальной, в .env должно быть:" -ForegroundColor Yellow
Write-Host "  CONTENT_FACTORY_DRY_RUN=false"
Write-Host "и бот должен быть администратором каналов."
