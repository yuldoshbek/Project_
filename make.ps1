# Windows-обёртка над Makefile: цели те же, синтаксис .\make.ps1 <цель>.
# Нужна потому, что make в Windows по умолчанию нет, а команда работает на обеих системах.
# Канонический список целей — в Makefile; при изменении правьте оба файла.

param(
    [Parameter(Position = 0)]
    [string]$Target = 'help'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Invoke-In {
    param([string]$Dir, [string]$Exe, [string[]]$CmdArgs)
    Push-Location $Dir
    try {
        & $Exe @CmdArgs
        if ($LASTEXITCODE -ne 0) { throw "$Exe $($CmdArgs -join ' ') завершилась с кодом $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

switch ($Target) {
    'help' {
        Write-Output @'
  install    Установить зависимости backend и frontend
  up         Поднять postgres, redis, minio, mailhog
  down       Остановить окружение
  logs       Логи окружения
  migrate    Применить миграции
  seed       Загрузить справочники и демо-данные
  dev-back   Запустить backend на :8000
  dev-front  Запустить frontend на :5173
  test       Прогнать все тесты
  check      Линтеры и типы
  fmt        Отформатировать код
  clean      Удалить кеши и артефакты сборки
'@
    }
    'install' {
        Invoke-In $backend 'uv' @('sync', '--all-groups')
        Invoke-In $frontend 'npm' @('ci')
    }
    'up' { Invoke-In $root 'docker' @('compose', 'up', '-d') }
    'down' { Invoke-In $root 'docker' @('compose', 'down') }
    'logs' { Invoke-In $root 'docker' @('compose', 'logs', '-f') }
    'migrate' { Invoke-In $backend 'uv' @('run', 'alembic', 'upgrade', 'head') }
    'seed' { Invoke-In $backend 'uv' @('run', 'python', '-m', 'app.seed') }
    'dev-back' { Invoke-In $backend 'uv' @('run', 'uvicorn', 'app.main:app', '--reload', '--port', '8000') }
    'dev-front' { Invoke-In $frontend 'npm' @('run', 'dev') }
    'test' {
        Invoke-In $backend 'uv' @('run', 'pytest')
        Invoke-In $frontend 'npm' @('run', 'test')
    }
    'check' {
        Invoke-In $backend 'uv' @('run', 'ruff', 'check', '.')
        Invoke-In $backend 'uv' @('run', 'ruff', 'format', '--check', '.')
        Invoke-In $backend 'uv' @('run', 'mypy', 'app', 'tests')
        Invoke-In $backend 'uv' @('run', 'lint-imports')
        Invoke-In $frontend 'npm' @('run', 'lint')
        Invoke-In $frontend 'npm' @('run', 'typecheck')
        Invoke-In $frontend 'npm' @('run', 'fmt:check')
    }
    'fmt' {
        Invoke-In $backend 'uv' @('run', 'ruff', 'format', '.')
        Invoke-In $backend 'uv' @('run', 'ruff', 'check', '--fix', '.')
        Invoke-In $frontend 'npm' @('run', 'fmt')
    }
    'clean' {
        foreach ($p in '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov', '.coverage') {
            $full = Join-Path $backend $p
            if (Test-Path $full) { Remove-Item -Recurse -Force $full }
        }
        foreach ($p in 'dist', 'coverage') {
            $full = Join-Path $frontend $p
            if (Test-Path $full) { Remove-Item -Recurse -Force $full }
        }
    }
    default {
        Write-Error "Неизвестная цель: $Target. Список целей: .\make.ps1 help"
        exit 1
    }
}
