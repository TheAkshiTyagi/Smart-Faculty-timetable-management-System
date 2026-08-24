# Smart Faculty Lecture & Timetable Management System

A portfolio-ready full-stack timetable application for finding **which teacher teaches which class, which subject, at what time, and in which room**.

## Stack
- Frontend: React + Vite + TypeScript + Tailwind CSS
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL (SQLite fallback for quick local demo)
- Auth: JWT
- Docker Compose

## Quick start

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Demo login
- Admin: admin@demo.com / admin123
- Teacher: teacher@demo.com / teacher123
- Student: student@demo.com / student123

The backend automatically creates demo data on first startup.

## PostgreSQL with Docker

```bash
docker compose up --build
```

Frontend: http://localhost:5173  
Backend: http://localhost:8000  
Swagger: http://localhost:8000/docs

## Core features
- Teacher/class/subject/room search
- Today's and weekly timetable
- Current and next lecture
- Free teacher and room lookup
- Backend timetable conflict detection
- Role-based JWT authentication
- Admin CRUD for timetable records
- CSV import
- Demo seed data


## V2 upgrades
- Full weekly timetable page
- Admin lecture creation/deletion
- Conflict rejection UI
- Free teacher/room finder
- Deterministic natural-language timetable queries
- CSV import page
- CSV export + print-friendly timetable
- Deployment and presentation guides
