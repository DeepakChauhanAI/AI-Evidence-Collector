@echo off
REM Launches backend + frontend in one Windows Terminal window, two tabs.
set ROOT=%~dp0
wt ^
  new-tab --title Backend  -d "%ROOT%backend"  cmd /k ".venv\Scripts\uvicorn app.main:app --reload --env-file .env" ^
; new-tab --title Frontend -d "%ROOT%frontend" cmd /k "npm run dev"
