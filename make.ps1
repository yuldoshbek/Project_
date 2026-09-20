# Windows-обёртка над Makefile: цели те же, синтаксис .\make.ps1 <цель>.
# Нужна потому, что make в Windows по умолчанию нет, а работать надо на обеих системах.
# Канонический список целей — в Makefile; при изменении правьте оба файла.

param(
    [Parameter(Position = 0)]
    [string]$Target = 'help',

    # Описание для revision, имя задачи для job.
    [Parameter(Position = 1)]
    [string]$Name
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

# Frontend вызывается через npm.cmd, а не npm: в Windows `npm` разрешается в npm.ps1,
# а тот собирает команду строкой и ломается на кавычках в аргументах.
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
  doctor     Проверить машину перед работой: контейнер, порты, .env, миграции
  install    Установить зависимости backend и frontend
  up         Поднять PostgreSQL для разработки
  down       Остановить окружение (данные сохраняются)
  reset      Остановить окружение и удалить данные
  logs       Логи окружения
  migrate    Применить миграции
  revision   Создать миграцию: .\make.ps1 revision "описание"
  heads      Проверить, что голова миграций одна
  seed       Загрузить справочники
  job        Выполнить задачу: .\make.ps1 job morning-summary
  dev-back   Запустить backend на :8000
  dev-front  Запустить frontend на :5173
  test       Прогнать все тесты
  e2e        Playwright на локальной сборке
  check      Линтеры, типы и проверка документов
  docs       Проверить документы
  fmt        Отформатировать код
  reqs       Пересобрать backend/requirements.txt из uv.lock
  clean      Удалить кеши и артефакты сборки
'@
    }
    'doctor' { Invoke-In $root 'python' @('scripts/doctor.py') }
    'install' {
        Invoke-In $backend 'uv' @('sync', '--all-groups')
        Invoke-In $frontend 'npm.cmd' @('ci')
    }
    'up' { Invoke-In $root 'docker' @('compose', 'up', '-d', '--wait') }
    'down' { Invoke-In $root 'docker' @('compose', 'down') }
    'reset' { Invoke-In $root 'docker' @('compose', 'down', '-v') }
    'logs' { Invoke-In $root 'docker' @('compose', 'logs', '-f') }
    'migrate' { Invoke-In $backend 'uv' @('run', 'alembic', 'upgrade', 'head') }
    'revision' {
        if (-not $Name) { throw 'укажите описание: .\make.ps1 revision "добавить проекты"' }
        Invoke-In $backend 'uv' @('run', 'alembic', 'revision', '--autogenerate', '-m', $Name)
        Write-Output 'проверьте сгенерированное: автогенерация не видит переименований и данных'
    }
    'heads' { Invoke-In $backend 'uv' @('run', 'alembic', 'heads') }
    'seed' { Invoke-In $backend 'uv' @('run', 'python', '-m', 'app.seed') }
    'job' {
        if (-not $Name) { throw 'укажите задачу: .\make.ps1 job morning-summary' }
        Invoke-In $backend 'uv' @('run', 'python', '-m', 'app.jobs.run', $Name)
    }
    'dev-back' { Invoke-In $backend 'uv' @('run', 'uvicorn', 'app.main:app', '--reload', '--port', '8000') }
    'dev-front' { Invoke-In $frontend 'npm.cmd' @('run', 'dev') }
    'test' {
        Invoke-In $backend 'uv' @('run', 'pytest')
        Invoke-In $frontend 'npm.cmd' @('run', 'test')
    }
    'e2e' { Invoke-In $frontend 'npx.cmd' @('playwright', 'test') }
    'check' {
        Invoke-In $backend 'uv' @('run', 'ruff', 'check', '.')
        Invoke-In $backend 'uv' @('run', 'ruff', 'format', '--check', '.')
        Invoke-In $backend 'uv' @('run', 'mypy', 'app', 'tests')
        Invoke-In $backend 'uv' @('run', 'lint-imports')
        Invoke-In $frontend 'npm.cmd' @('run', 'lint')
        Invoke-In $frontend 'npm.cmd' @('run', 'lint:css')
        Invoke-In $frontend 'npm.cmd' @('run', 'typecheck')
        Invoke-In $frontend 'npm.cmd' @('run', 'fmt:check')
        Invoke-In $root 'python' @('scripts/check_docs.py')
    }
    'docs' { Invoke-In $root 'python' @('scripts/check_docs.py') }
    'fmt' {
        Invoke-In $backend 'uv' @('run', 'ruff', 'format', '.')
        Invoke-In $backend 'uv' @('run', 'ruff', 'check', '--fix', '.')
        Invoke-In $frontend 'npm.cmd' @('run', 'fmt')
    }
    'reqs' {
        Invoke-In $backend 'uv' @('export', '--frozen', '--no-dev', '--no-emit-project', '--no-hashes', '-o', 'requirements.txt')
    }
    'clean' {
        foreach ($p in '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov', '.coverage') {
            $full = Join-Path $backend $p
            if (Test-Path $full) { Remove-Item -Recurse -Force $full }
        }
        foreach ($p in 'dist', 'coverage', 'playwright-report', 'test-results') {
            $full = Join-Path $frontend $p
            if (Test-Path $full) { Remove-Item -Recurse -Force $full }
        }
    }
    default {
        Write-Error "Неизвестная цель: $Target. Список целей: .\make.ps1 help"
        exit 1
    }
}
