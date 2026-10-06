@echo off
title PPT Market V3
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
call .venv\Scripts\python.exe app.py
pause
