@echo off
rem =====================================================================
rem  Запуск контент-завода в Windows.
rem
rem  Двойной клик или из командной строки:
rem      scripts\windows\run.bat              - демон по расписанию
rem      scripts\windows\run.bat --once       - одна проверка и выход
rem      scripts\windows\run.bat --interval 300
rem
rem  Скрипт сам переходит в корень проекта и использует Python из .venv.
rem  Остановка демона: Ctrl+C.
rem =====================================================================
setlocal

set "ROOT=%~dp0..\.."
pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: не удалось перейти в каталог проекта: %ROOT%
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo ОШИБКА: не найдено виртуальное окружение .venv.
    echo Сначала выполните установку:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate
    echo     python -m pip install -r requirements.txt
    popd
    exit /b 1
)

if not exist "data\logs" mkdir "data\logs" >nul 2>&1

echo ====================================================================
echo  Контент-завод: запуск
echo  Проект: %ROOT%
echo  Остановка: Ctrl+C
echo ====================================================================

".venv\Scripts\python.exe" -m content_factory daemon %*
set "RC=%ERRORLEVEL%"

popd
exit /b %RC%
