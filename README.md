# 🚨 Risk Radar — Real-Time Fraud & Anomaly Detection Dashboard

**A real-time transaction monitoring and anomaly detection platform built with React, FastAPI, Python, SQLite, and Machine Learning.**

[![React](https://img.shields.io/badge/Frontend-React-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Python](https://img.shields.io/badge/Backend-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Machine Learning](https://img.shields.io/badge/ML-Anomaly%20Detection-orange)](#machine-learning)
[![Database](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

## 🔗 Project Links

- **GitHub Repository:** https://github.com/pawankumargupta9142-glitch/real-time-anomaly-detection-dashboard
- **Local Application:** http://127.0.0.1:5181
- **Local API:** http://127.0.0.1:8000
- **API Documentation:** http://127.0.0.1:8000/docs

> The application links above are for local development. A publicly hosted demo is not configured by this README.

## 📌 Overview

Risk Radar is a transaction monitoring dashboard designed to identify unusual activity using machine-learning-based anomaly detection.

The platform combines a web dashboard, a Python API, a transaction-processing pipeline, and a live event stream to help users inspect events, review risk scores, and investigate potentially suspicious activity.

The project is intended for educational purposes, demonstrations, and further development of fraud and anomaly monitoring systems.

## ✨ Features

- **Interactive Dashboard:** Monitor transaction activity and risk-related metrics.
- **Live Event Monitoring:** View incoming events using WebSocket communication.
- **Event Timeline:** Search, filter, and inspect transaction and system events.
- **CSV Transaction Import:** Upload supported transaction CSV files for analysis.
- **Anomaly Detection:** Use the existing machine-learning model to score events.
- **Risk Classification:** Display risk scores and risk levels.
- **Alerts:** Review events that meet the application's configured alert rules.
- **Analytics:** Explore transaction activity and anomaly trends.
- **REST API:** Communicate between the React frontend and FastAPI backend.
- **Local Persistence:** Store application data using SQLite.

Feature availability and results depend on the current application configuration and successful backend execution.

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, JavaScript, Vite |
| Backend | Python, FastAPI |
| Machine Learning | Existing anomaly-detection model |
| Database | SQLite |
| Real-time Communication | WebSocket |
| API Communication | REST API |
| Testing | Python unittest, frontend production build |
| Version Control | Git and GitHub |

## 🏗️ Architecture

```text
                 User
                  |
                  v
        React + Vite Frontend
                  |
          REST API / WebSocket
                  |
                  v
           FastAPI Backend
                  |
          +-------+--------+
          |                |
          v                v
    CSV Processing    Event Simulator
          |                |
          +-------+--------+
                  |
                  v
          ML Anomaly Detection
                  |
                  v
            SQLite Database
                  |
                  v
      Events, Alerts, Analytics
```

## 📂 Project Structure

```text
real-time-anomaly-detection-dashboard/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routes/
│   ├── services/
│   ├── tests/
│   ├── models_store/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── context/
│   │   ├── pages/
│   │   └── utils/
│   ├── package.json
│   └── .env.example
├── docs/
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── LICENSE
└── README.md
```

Some filenames or folders may vary depending on the current project version.

## ⚙️ Installation and Setup

### Prerequisites

Install the following:

- Python 3.12 or another version supported by the project's dependencies
- Node.js and npm
- Git
- Visual Studio Code (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/pawankumargupta9142-glitch/real-time-anomaly-detection-dashboard.git
cd real-time-anomaly-detection-dashboard
```

### 2. Set up the backend

Open a terminal in the project root.

**Windows PowerShell:**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configure environment variables using the project's `.env.example` as a guide. Create a local `.env` file if required by the application. Never commit actual secrets.

Start FastAPI:

```powershell
python -m uvicorn main:app --reload --port 8000
```

Backend API:

- API: http://127.0.0.1:8000
- Swagger documentation: http://127.0.0.1:8000/docs

### 3. Set up the frontend

Open a second terminal:

```powershell
cd frontend
npm install
```

Configure the frontend environment variables according to `frontend/.env.example`, if required. Set the API and WebSocket URLs to match the backend configuration.

Start Vite:

```powershell
npm run dev
```

Open the exact local URL printed by Vite. The development port may vary if the default port is unavailable.

## 📊 CSV Transaction Import

The Events page provides a CSV import interface for supported transaction formats.

### Risk Radar CSV format

```csv
event_type,user_id,amount
Payment,USR-0001,250.50
Transaction,USR-0002,1200.00
Payment,USR-0003,75.25
```

### Import workflow

1. Open the Events page.
2. Select a supported CSV file.
3. Click **Upload and analyze**.
4. Review the import summary.
5. Inspect analyzed events and their model-generated risk classifications.

The current importer is configured for a maximum file size of 10 MB and a maximum of 50,000 data rows per upload. Other validation rules and accepted event types are determined by the backend implementation.

CSV ground-truth labels, when present and supported, must remain separate from model predictions.

## 🤖 Machine Learning

Risk Radar uses its existing anomaly-detection pipeline to analyze transaction events and identify unusual patterns.

The dashboard can display model-generated risk scores and anomaly classifications to support investigation.

**Important limitations:**

- An anomaly is not necessarily fraud.
- Synthetic data is not equivalent to real banking data.
- Risk scores should not be interpreted as calibrated fraud probabilities unless calibration has been evaluated.
- Model quality should be assessed with an appropriate test dataset and metrics such as precision, recall, F1-score, and false-positive rate when ground-truth labels are available.

## 🧪 Testing

### Backend tests

From the project root:

```powershell
cd backend
python -m unittest discover -s tests -v
```

Run tests in the project's configured Python environment.

### Frontend production build

From the project root:

```powershell
npm run build --prefix frontend
```

### Git whitespace check

```bash
git diff --check
```

Record the latest test results before presenting or releasing a new version.

## 🔒 Security Notes

- Keep API keys, passwords, and private environment variables out of GitHub.
- Do not commit local databases containing private or sensitive records.
- Validate CSV uploads before processing.
- Protect database writes against partial failures.
- Apply authentication and authorization to protected endpoints where required.
- Use HTTPS and appropriate production configuration before public deployment.

## 🚀 Future Improvements

- Improve model evaluation with documented benchmark results.
- Add transaction investigation details and explainable anomaly indicators.
- Improve CSV import reporting and duplicate-import protection.
- Add exportable analytics and reports.
- Add role-based access control and audit trails.
- Add production deployment, monitoring, and automated CI tests.

## 🎓 Project Purpose

Risk Radar is a learning and demonstration project exploring real-time event monitoring, transaction analysis, REST APIs, WebSockets, database persistence, and machine-learning-based anomaly detection.

It is not a certified banking fraud-prevention system.

## 👨‍💻 Repository

Explore the source code, review the implementation, and follow future improvements:

**[Open Risk Radar on GitHub](https://github.com/pawankumargupta9142-glitch/real-time-anomaly-detection-dashboard)**

If you find the project useful, consider starring the repository.

---

**Built with React, Python, FastAPI, SQLite, and Machine Learning.**
