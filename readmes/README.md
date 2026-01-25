# SQL Assistant

SQL Assistant is a FastAPI-based backend with a simple HTML/CSS frontend for interacting with databases using AI.

---

## 🚀 Setup Instructions

### 1. Prerequisites
- Install **Python 3.11.9**
- Use either:
  - **venv** (recommended for lightweight environments), or
  - **Anaconda** (if you prefer managing environments with conda)

---

### 2. Create and Activate Virtual Environment

#### Using venv
```bash
# Activate on Linux
python3 -m venv venv
source venv/bin/activate
nano ~/.bashrc
# add below logics in last:
if [ -f "$PWD/venv/bin/activate" ]; then
    source "$PWD/venv/bin/activate"
fi
if [ -f "$PWD/myvenv/bin/activate" ]; then
    source "$PWD/myvenv/bin/activate"
fi

# Activate on Windows
python -m venv venv
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
notepad $PROFILE
# Auto-activate venv if exists
if (Test-Path "$PWD\venv\Scripts\Activate.ps1") {
    & "$PWD\venv\Scripts\Activate.ps1"
}
if (Test-Path "$PWD\myvenv\Scripts\Activate.ps1") {
    & "$PWD\myvenv\Scripts\Activate.ps1"
}

# Activate on Mac OS
python -m venv venv
source venv/bin/activate
nano ~/.zshrc
# Auto-activate venv if exists
if [ -f "$PWD/venv/bin/activate" ]; then
    source "$PWD/venv/bin/activate"
fi
if [ -f "$PWD/myvenv/bin/activate" ]; then
    source "$PWD/myvenv/bin/activate"
fi

#### Using Anaconda

```bash
conda create -n sqlassistant python=3.11.9
conda activate sqlassistant
```

---

### 3. Install Dependencies

```bash
pip install -r requirement.txt
```

---

### 4. Configure Environment

 Create a `.env` file in the project root with following key:

```ini
DYNACONF_ENV=development  # production/development
```

#### Create a `.secrets.toml` file in the project root with below keys:

```toml
[default]
OPENAI_API_KEY = ""
GROQ_API_KEY   = ""
DB_SERVER      = ""  # server name where database is hosted
DB_NAME        = ""

[production]
# Add production-specific overrides here
```

⚠️ **Note:** If the database is not available, please reach out to **Hussain** for help setting up the DB.

---

### 5. Configuration

Project configuration is stored in **`settings.toml`**.

* Update the file to modify server details such as port.

---

### 6. Run Backend

Start the FastAPI backend server:

```bash
python app.py
```

* The server runs by default on **port 5011**.
* To change the port, update `settings.toml` and rerun:

  ```bash
  python app.py
  ```

---

## 7. 📌 Notes

* Backend: FastAPI (Python 3.11.9)
* Frontend: Mobile Application
* Configuration: Dynaconf (`settings.toml`, `.secrets.toml`)

## 8.  Run Application Automatically when server will turn ON.

* Press Win + R, type cmd, and press Enter.
* Nevigate to the .bat file and copy the exact path with file name ane enter this path to the cmd to run tha app parmanently.

## 10. For Web configuration
* web.config file contains the configurations to run the uvicorn app publically.

