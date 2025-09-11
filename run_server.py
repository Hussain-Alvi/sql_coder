# run_server.py
import webbrowser
import uvicorn
import os

if __name__ == "__main__":
    port = 8000
    url = f"http://127.0.0.1:{port}/docs"
    # find module name (api.py)
    filename = os.path.splitext(os.path.basename("api.py"))[0]
    print(f"Starting server at {url}")
    webbrowser.open(url)
    uvicorn.run(f"{filename}:app", host="127.0.0.1", port=port, reload=False)
