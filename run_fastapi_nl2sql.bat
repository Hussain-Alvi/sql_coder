@echo off
cd C:\RM2GO_AI_1.0\Mobile_App
#python -m venv venv
#call venv\Scripts\activate
C:\Users\DELL\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn app:app --host 0.0.0.0 --port 5011 --workers 2
