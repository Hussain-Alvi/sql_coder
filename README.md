# SQL Assistant

SQL Assistant is a FastAPI-based backend with a simple HTML/CSS frontend for interacting with databases using AI.

---

## 🚀 Setup Instructions

### 1. Prerequisites
- Install **Python 3.10**
- Use either:
  - **venv** (recommended for lightweight environments), or
  - **Anaconda** (if you prefer managing environments with conda)

---

### 2. Create and Activate Virtual Environment

#### Using venv
```bash
python3.10 -m venv venv
# Activate on Linux/Mac
source venv/bin/activate
# Activate on Windows
venv\Scripts\activate
````

#### Using Anaconda

```bash
conda create -n sqlassistant python=3.10
conda activate sqlassistant
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
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
OPENAI_API_KEY = "key"
GROQ_API_KEY   = "key"
DB_SERVER      = "HAMIDWORKPC"  # server name where database is hosted
DB_NAME        = "itsdrystock"

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

### 7. Run Frontend

The frontend is implemented in **HTML + CSS**.

* Open `index.html` in your browser.
* Update the `BASE_URL` inside `index.html` to point to your FastAPI backend server.

---

## 📌 Notes

* Backend: FastAPI (Python 3.10)
* Frontend: HTML + CSS
* Configuration: Dynaconf (`settings.toml`, `.env`, `.secrets.toml`)

