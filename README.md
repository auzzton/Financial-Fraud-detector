# Financial Fraud Detection - Runbook

End-to-end fraud detection platform with:
- Kafka transaction streaming
- FastAPI consumer + rules + ML scoring
- PostgreSQL persistence
- Redis enrichment counters
- Next.js real-time dashboard
- MLflow model tracking/registry

---

## 1) Prerequisites

- Windows 10/11
- Docker Desktop running
- Python 3.12+
- Node.js 18+ and npm

---

## 2) First-Time Setup (from scratch)

Run in PowerShell from project root:

```powershell
cd "C:\Projects\Financial fraud detection"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

---

## 3) Start Infrastructure

From project root:

```powershell
cd "C:\Projects\Financial fraud detection"
docker compose up -d
```

`docker-compose.yml` starts:
- Postgres (`fraud_db`)
- Zookeeper
- Kafka
- Redis (`fraud_redis`)

The FastAPI app reads Redis at `localhost:6379`, so ensure Redis is available on host `6379`.
If your compose setup does not expose Redis port, start host Redis too:

```powershell
docker run -d --name fraud_redis_host -p 6379:6379 redis:7-alpine
```

Apply migration safely (idempotent):

```powershell
docker exec -i fraud_db psql -U admin -d fraud_db -c "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_fraud BOOLEAN DEFAULT NULL;"
```

---

## 4) Start Application Services

Use **separate terminals**.

### Terminal A - MLflow
```powershell
cd "C:\Projects\Financial fraud detection"
.\venv\Scripts\Activate.ps1
python -m mlflow server --host 0.0.0.0 --port 5000
```

### Terminal B - FastAPI consumer
```powershell
cd "C:\Projects\Financial fraud detection\consumer"
..\venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Terminal C - Frontend
```powershell
cd "C:\Projects\Financial fraud detection\frontend"
npm run dev
```

### Terminal D - Producer (live transactions)
```powershell
cd "C:\Projects\Financial fraud detection"
.\venv\Scripts\Activate.ps1
python producer.py
```

---

## 5) URLs

- Frontend dashboard: [http://localhost:3000](http://localhost:3000)
- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- MLflow: [http://localhost:5000](http://localhost:5000)

---

## 6) Phase 5 Workflow (Unsupervised -> Supervised)

1. Start producer and let transactions stream.
2. In the UI:
   - Expand transactions in live feed.
   - Label using:
     - `Mark True Fraud`
     - `Dismiss / False Positive`
3. Collect at least 50 labeled transactions (`is_fraud` true/false).
4. Run training:

```powershell
cd "C:\Projects\Financial fraud detection"
.\venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING='utf-8'
python ml/train.py
```

Training behavior:
- `< 50` labels -> trains `IsolationForest` and registers `fraud_iforest`
- `>= 50` labels -> trains `RandomForestClassifier` and registers `fraud_classifier`

5. Restart FastAPI consumer so it reloads latest model:

```powershell
cd "C:\Projects\Financial fraud detection\consumer"
..\venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The consumer tries:
1. `models:/fraud_classifier/latest`
2. fallback `models:/fraud_iforest/latest`

---

## 7) Useful Checks

### API health
```powershell
python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/', timeout=10).read().decode())"
```

### Report summary
```powershell
python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/reports/summary', timeout=20).read().decode())"
```

### Lint frontend
```powershell
cd "C:\Projects\Financial fraud detection\frontend"
npm run lint
```

---

## 8) Stop Everything

Stop app processes with `Ctrl + C` in each terminal first.

Then stop containers:

```powershell
cd "C:\Projects\Financial fraud detection"
docker compose down
docker rm -f fraud_redis_host
```

---

## 9) Quick Restart Commands

If dependencies are already installed:

1. `docker compose up -d`
2. `python -m mlflow server --host 0.0.0.0 --port 5000`
3. `python -m uvicorn main:app --host 0.0.0.0 --port 8000` (from `consumer`)
4. `npm run dev` (from `frontend`)
5. `python producer.py`

---

## 10) Easy Mode (One-Command Start/Stop)

From project root:

### Start everything
```powershell
cd "C:\Projects\Financial fraud detection"
.\start.ps1
```

### Stop everything
```powershell
cd "C:\Projects\Financial fraud detection"
.\stop.ps1
```

If PowerShell blocks scripts the first time:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

ye