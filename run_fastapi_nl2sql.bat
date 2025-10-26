@echo off
cd e:\Websites\qa-rm2goai.appinsnap.com
#python -m venv venv
#call venv\Scripts\activate
C:\Users\adminnoadmin\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn app:app --host 127.0.0.1 --port 5011 --workers 2
