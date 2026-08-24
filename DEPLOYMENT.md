# Deployment Guide

## Recommended
- GitHub: source code
- Render: FastAPI + PostgreSQL
- Vercel: React frontend

### Backend on Render
Create a PostgreSQL database and a Web Service from `/backend`.
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment:
- DATABASE_URL = Render PostgreSQL URL
- JWT_SECRET = long random secret
- CORS_ORIGINS = your Vercel URL

### Frontend on Vercel
Root directory: `frontend`
Build: `npm run build`
Output: `dist`
Environment:
`VITE_API_URL=https://YOUR-BACKEND.onrender.com`

## Presentation
Demo flow:
1. Login as Student
2. Show current lecture
3. Ask: "Who is teaching CSE-A at 11 AM?"
4. Show weekly timetable
5. Show free teacher/room finder
6. Login as Admin
7. Create a conflicting lecture and show rejection
8. Import CSV
9. Export/print weekly timetable
10. Open FastAPI `/docs`

For a projector, use browser full-screen and the Weekly Timetable page.
