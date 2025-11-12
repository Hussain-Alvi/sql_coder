@echo off
cd e:\Websites\qa-rm2goai.appinsnap.com
call venv\Scripts\activate
uvicorn app:app --host 0.0.0.0 --port 5011