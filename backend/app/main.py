from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, time
from zoneinfo import ZoneInfo
import csv, io

INDIA_TZ = ZoneInfo("Asia/Kolkata")

def india_now():
    return datetime.now(INDIA_TZ)

from .database import Base, engine, get_db
from .models import *
from .schemas import Login, Token, UserOut, LectureCreate, LectureOut, Register, FeedbackCreate, TeacherNoteCreate
from .auth import verify_password, create_token, current_user, require_role, hash_password
from .services import conflicts, lecture_payload
from .seed import seed

app = FastAPI(title="Smart Faculty Timetable API", version="1.0.0")

origins = [x.strip() for x in __import__("os").getenv("CORS_ORIGINS","http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite migration for databases created by older v5 builds.
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "notifications" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("notifications")}
        if "recipient_user_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN recipient_user_id INTEGER"))
    db=next(get_db())
    try: seed(db)
    finally: db.close()

@app.get("/")
def root():
    return {"message":"Smart Faculty Timetable API","docs":"/docs"}

@app.post("/auth/login", response_model=Token)
def login(data: Login, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.email==data.email).first()
    if not user or not verify_password(data.password,user.password_hash):
        raise HTTPException(401,"Invalid email or password")
    return {"access_token":create_token(user),"token_type":"bearer"}

@app.get("/auth/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user

@app.post("/auth/register", response_model=UserOut)
def register(data: Register, db: Session=Depends(get_db)):
    if db.query(User).filter(User.email==data.email).first():
        raise HTTPException(409, "An account with this email already exists.")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    if data.role == Role.STUDENT and not data.class_id:
        raise HTTPException(400, "Select a class for a student account.")
    if data.role == Role.STUDENT and not data.enrollment_number:
        raise HTTPException(400, "Enrollment number is required for students.")
    if data.role == Role.TEACHER and not data.employee_id:
        raise HTTPException(400, "Employee ID is required for teachers.")
    if data.class_id and not db.get(ClassRoomGroup, data.class_id):
        raise HTTPException(400, "Selected class does not exist.")
    u=User(name=data.name.strip(), email=data.email, password_hash=hash_password(data.password), role=data.role)
    db.add(u); db.flush()
    if data.role == Role.STUDENT:
        if db.query(Student).filter(Student.enrollment_number==data.enrollment_number).first():
            db.rollback(); raise HTTPException(409, "Enrollment number already exists.")
        db.add(Student(user_id=u.id, enrollment_number=data.enrollment_number.strip(), class_id=data.class_id))
    elif data.role == Role.TEACHER:
        if db.query(Teacher).filter(Teacher.employee_id==data.employee_id).first():
            db.rollback(); raise HTTPException(409, "Employee ID already exists.")
        dept=db.query(Department).first()
        db.add(Teacher(user_id=u.id, employee_id=data.employee_id.strip(), department_id=dept.id, designation=data.designation or "Assistant Professor"))
    db.commit(); db.refresh(u); return u

@app.get("/register/classes")
def register_classes(db: Session=Depends(get_db)):
    return [{"id":c.id,"name":f"{c.name}-{c.section}","semester":c.semester} for c in db.query(ClassRoomGroup).order_by(ClassRoomGroup.name,ClassRoomGroup.section).all()]

@app.post("/feedback")
def create_feedback(data: FeedbackCreate, db: Session=Depends(get_db), user=Depends(current_user)):
    if user.role == Role.ADMIN:
        raise HTTPException(403, "Admins receive feedback; they do not submit feedback from this section.")
    if data.rating < 1 or data.rating > 5: raise HTTPException(400, "Rating must be between 1 and 5.")
    if not data.message.strip(): raise HTTPException(400, "Feedback message is required.")
    row=Feedback(user_id=user.id, rating=data.rating, message=data.message.strip())
    db.add(row); db.commit(); return {"message":"Thank you for your feedback!"}

@app.get("/feedback")
def list_feedback(db: Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    rows=[]
    for x in db.query(Feedback).order_by(Feedback.created_at.desc()).all():
        sender=db.get(User,x.user_id)
        rows.append({"id":x.id,"rating":x.rating,"message":x.message,"user":sender.name if sender else "Unknown","role":sender.role.value if sender else "","created_at":x.created_at.isoformat()})
    return rows

@app.post("/teacher-notes")
def send_teacher_note(data: TeacherNoteCreate, db: Session = Depends(get_db), user=Depends(require_role(Role.TEACHER))):
    message = data.message.strip()
    if not message: raise HTTPException(400, "Message is required.")
    if len(message) > 1200: raise HTTPException(400, "Message must be 1200 characters or less.")
    audience_values = {x.value for x in data.audience}
    audience_values.discard("TEACHER")
    if not audience_values: raise HTTPException(400, "Choose Student, Admin, or both.")
    if "ADMIN" in audience_values:
        db.add(Notification(sender_user_id=user.id, recipient_role=NotificationAudience.ADMIN, message=message))
    if "STUDENT" in audience_values:
        db.add(Notification(sender_user_id=user.id, recipient_role=NotificationAudience.STUDENT, message=message))
    db.commit()
    return {"message": "Note sent successfully.", "audience": sorted(audience_values)}

class AdminMessageCreate(__import__("pydantic").BaseModel):
    audience: str
    message: str
    teacher_user_id: int | None = None

@app.post("/admin-messages")
def send_admin_message(data: AdminMessageCreate, db: Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    message=data.message.strip()
    if not message: raise HTTPException(400,"Message is required.")
    if len(message)>1200: raise HTTPException(400,"Message must be 1200 characters or less.")
    recipients=[]
    if data.audience == "ALL_STUDENTS":
        recipients=[u.id for u in db.query(User).filter(User.role==Role.STUDENT, User.is_active==True).all()]
    elif data.audience == "ALL_TEACHERS":
        recipients=[u.id for u in db.query(User).filter(User.role==Role.TEACHER, User.is_active==True).all()]
    elif data.audience == "TEACHER":
        target=db.get(User,data.teacher_user_id) if data.teacher_user_id else None
        if not target or target.role != Role.TEACHER: raise HTTPException(400,"Select a valid teacher.")
        recipients=[target.id]
    elif data.audience == "ALL":
        recipients=[u.id for u in db.query(User).filter(User.role.in_([Role.STUDENT,Role.TEACHER]), User.is_active==True).all()]
    else:
        raise HTTPException(400,"Choose students, all teachers, or a specific teacher.")
    if not recipients: raise HTTPException(400,"No active recipients found.")
    db.add_all([Notification(sender_user_id=user.id, recipient_user_id=uid, message=message) for uid in recipients])
    db.commit()
    return {"message":"Message sent successfully.","recipients":len(recipients)}

@app.get("/notifications")
def notifications(db: Session = Depends(get_db), user=Depends(current_user)):
    audience_map={Role.ADMIN:NotificationAudience.ADMIN, Role.STUDENT:NotificationAudience.STUDENT, Role.TEACHER:NotificationAudience.TEACHER}
    audience=audience_map[user.role]
    rows=db.query(Notification).filter(
        Notification.is_active == True,
        or_(Notification.recipient_user_id == user.id, Notification.recipient_role == audience),
    ).order_by(Notification.created_at.desc()).limit(20).all()
    return [{
        "id": x.id, "message": x.message,
        "sender": db.get(User,x.sender_user_id).name if db.get(User,x.sender_user_id) else "Admin",
        "created_at": x.created_at.isoformat(),
    } for x in rows]

@app.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    audience_map={Role.ADMIN:NotificationAudience.ADMIN, Role.STUDENT:NotificationAudience.STUDENT, Role.TEACHER:NotificationAudience.TEACHER}
    audience=audience_map[user.role]
    row=db.query(Notification).filter(Notification.id==notification_id, or_(Notification.recipient_user_id==user.id, Notification.recipient_role==audience)).first()
    if not row: raise HTTPException(404,"Notification not found.")
    row.is_active=False; db.commit(); return {"message":"Notification marked as read."}

@app.get("/lectures")
def lectures(day: str|None=None, teacher_id:int|None=None, class_id:int|None=None, db:Session=Depends(get_db), user=Depends(current_user)):
    q=db.query(Lecture)
    if day: q=q.filter(Lecture.day_of_week==day.upper())
    if teacher_id: q=q.filter(Lecture.teacher_id==teacher_id)
    if class_id: q=q.filter(Lecture.class_id==class_id)
    return [lecture_payload(db,x) for x in q.order_by(Lecture.start_time).all()]

@app.post("/lectures", response_model=LectureOut)
def create_lecture(data: LectureCreate, db:Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    if data.start_time >= data.end_time:
        raise HTTPException(400,"Start time must be before end time.")
    issues=conflicts(db,data)
    if issues: raise HTTPException(409, issues)
    row=Lecture(**{**data.model_dump(), "day_of_week": data.day_of_week.upper()})
    db.add(row); db.commit(); db.refresh(row)
    return {**row.__dict__, **lecture_payload(db,row)}


@app.put("/lectures/{lecture_id}")
def update_lecture(lecture_id:int, data: LectureCreate, db:Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    row=db.get(Lecture, lecture_id)
    if not row: raise HTTPException(404,"Lecture not found")
    if data.start_time >= data.end_time:
        raise HTTPException(400,"Start time must be before end time.")
    issues=conflicts(db,data,exclude_id=lecture_id)
    if issues: raise HTTPException(409, issues)
    for k,v in data.model_dump().items(): setattr(row,k,v)
    row.day_of_week=data.day_of_week.upper()
    db.commit(); db.refresh(row)
    return lecture_payload(db,row)

@app.get("/analytics/workload")
def workload(db: Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    from collections import defaultdict
    rows=[]
    teachers=db.query(Teacher).all()
    for t in teachers:
        u=db.get(User,t.user_id)
        lectures=db.query(Lecture).filter(Lecture.teacher_id==t.id).all()
        minutes=sum((datetime.combine(datetime.today(),x.end_time)-datetime.combine(datetime.today(),x.start_time)).seconds//60 for x in lectures)
        rows.append({"id":t.id,"name":u.name if u else "Unknown","lectures":len(lectures),"hours":round(minutes/60,1)})
    rows.sort(key=lambda x:x["hours"], reverse=True)
    return rows

@app.get("/dashboard/stats")
def dashboard_stats(db:Session=Depends(get_db), user=Depends(current_user)):
    day=india_now().strftime("%A").upper()
    return {
        "teachers":db.query(Teacher).count(),
        "classes":db.query(ClassRoomGroup).count(),
        "subjects":db.query(Subject).count(),
        "rooms":db.query(Room).count(),
        "lectures_today":db.query(Lecture).filter(Lecture.day_of_week==day).count()
    }

@app.get("/timetable/weekly")
def weekly(db:Session=Depends(get_db), user=Depends(current_user)):
    # The Weekly Timetable is a shared college timetable. Every authenticated
    # role can view the complete schedule; role-specific filtering belongs in
    # dedicated class/teacher timetable endpoints.
    days=["MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY"]
    rows = db.query(Lecture).order_by(Lecture.start_time).all()
    return {d:[lecture_payload(db,x) for x in rows if x.day_of_week == d] for d in days}

@app.put("/lectures/{lecture_id}/substitute")
def substitute_teacher(lecture_id:int, teacher_id:int=Query(...), db:Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    """Assign a substitute teacher to one scheduled lecture.

    This changes only the selected lecture, so the original timetable time,
    class, subject and room remain unchanged.
    """
    row = db.get(Lecture, lecture_id)
    if not row:
        raise HTTPException(404, "Lecture not found")
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(404, "Substitute teacher not found")
    # Avoid assigning the same teacher to two overlapping lectures.
    conflict = db.query(Lecture).filter(
        Lecture.id != lecture_id,
        Lecture.teacher_id == teacher_id,
        Lecture.day_of_week == row.day_of_week,
        Lecture.start_time < row.end_time,
        Lecture.end_time > row.start_time,
    ).first()
    if conflict:
        raise HTTPException(409, "This substitute teacher already has a lecture at that time.")
    row.teacher_id = teacher_id
    db.commit(); db.refresh(row)
    return lecture_payload(db, row)

@app.get("/timetable/class/{class_id}")
def class_timetable(class_id:int, db:Session=Depends(get_db), user=Depends(current_user)):
    return [lecture_payload(db,x) for x in db.query(Lecture).filter(Lecture.class_id==class_id).order_by(Lecture.day_of_week,Lecture.start_time).all()]

@app.get("/timetable/teacher/{teacher_id}")
def teacher_timetable(teacher_id:int, db:Session=Depends(get_db), user=Depends(current_user)):
    return [lecture_payload(db,x) for x in db.query(Lecture).filter(Lecture.teacher_id==teacher_id).order_by(Lecture.day_of_week,Lecture.start_time).all()]

@app.get("/nl-query")
def natural_language_query(question:str=Query(min_length=3), db:Session=Depends(get_db), user=Depends(current_user)):
    """Deterministic natural-language timetable lookup; no external AI API required."""
    q=question.lower()
    import re
    teacher=None
    for t in db.query(Teacher).all():
        u=db.get(User,t.user_id)
        if u and u.name.lower() in q: teacher=t; break
    cls=None
    for c in db.query(ClassRoomGroup).all():
        label=f"{c.name}-{c.section}".lower()
        if label in q or (c.name.lower() in q and c.section.lower() in q): cls=c; break
    subject=None
    for s in db.query(Subject).all():
        if s.name.lower() in q or s.code.lower() in q: subject=s; break
    room=None
    for r in db.query(Room).all():
        if r.room_number.lower() in q: room=r; break
    days={"monday":"MONDAY","tuesday":"TUESDAY","wednesday":"WEDNESDAY","thursday":"THURSDAY","friday":"FRIDAY","saturday":"SATURDAY"}
    day=next((v for k,v in days.items() if k in q), None)
    hm=re.search(r'\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)?\b', q)
    target=None
    if hm:
        h=int(hm.group(1)); m=int(hm.group(2) or 0); ap=hm.group(3)
        if ap=="pm" and h<12:h+=12
        if ap=="am" and h==12:h=0
        target=time(h,m)
    rows=db.query(Lecture).all()
    out=[]
    for l in rows:
        if teacher and l.teacher_id!=teacher.id: continue
        if cls and l.class_id!=cls.id: continue
        if subject and l.subject_id!=subject.id: continue
        if room and l.room_id!=room.id: continue
        if day and l.day_of_week!=day: continue
        if target and not (l.start_time<=target<l.end_time): continue
        out.append(lecture_payload(db,l))
    return {"question":question,"answer":("Found "+str(len(out))+" matching lecture(s)." if out else "No matching lecture found."),"results":out}

@app.delete("/lectures/{lecture_id}")
def delete_lecture(lecture_id:int, db:Session=Depends(get_db), user=Depends(require_role(Role.ADMIN))):
    row=db.get(Lecture,lecture_id)
    if not row: raise HTTPException(404,"Lecture not found")
    db.delete(row); db.commit()
    return {"message":"Lecture deleted"}

def _visible_lectures_query(db:Session, user):
    q=db.query(Lecture)
    if user.role == Role.STUDENT:
        student=db.query(Student).filter(Student.user_id==user.id).first()
        if student: return q.filter(Lecture.class_id==student.class_id)
        return q
    if user.role == Role.TEACHER:
        teacher=db.query(Teacher).filter(Teacher.user_id==user.id).first()
        if teacher: return q.filter(Lecture.teacher_id==teacher.id)
        return q
    return q

@app.get("/timetable/today")
def today(db:Session=Depends(get_db), user=Depends(current_user)):
    day=india_now().strftime("%A").upper()
    rows=db.query(Lecture).filter(Lecture.day_of_week==day).order_by(Lecture.start_time).all()
    return {"day":day,"lectures":[lecture_payload(db,x) for x in rows]}

@app.get("/timetable/current")
def current(db:Session=Depends(get_db), user=Depends(current_user)):
    day=india_now().strftime("%A").upper()
    now=india_now().time()
    row=None
    for x in db.query(Lecture).filter(Lecture.day_of_week==day).all():
        if x.start_time <= now < x.end_time:
            row=x; break
    return {"current":lecture_payload(db,row) if row else None}

@app.get("/teachers")
def teachers(db:Session=Depends(get_db), user=Depends(current_user)):
    from .models import User
    rows=[]
    for t in db.query(Teacher).all():
        u=db.get(User,t.user_id)
        rows.append({"id":t.id,"user_id":u.id,"name":u.name,"employee_id":t.employee_id,"designation":t.designation})
    return rows

@app.get("/classes")
def classes(db:Session=Depends(get_db), user=Depends(current_user)):
    return [{"id":c.id,"name":f"{c.name}-{c.section}","semester":c.semester,"academic_year":c.academic_year} for c in db.query(ClassRoomGroup).all()]

@app.get("/subjects")
def subjects(db:Session=Depends(get_db), user=Depends(current_user)):
    return [{"id":s.id,"name":s.name,"code":s.code} for s in db.query(Subject).all()]

@app.get("/rooms")
def rooms(db:Session=Depends(get_db), user=Depends(current_user)):
    return [{"id":r.id,"room_number":r.room_number,"building":r.building,"capacity":r.capacity,"room_type":r.room_type} for r in db.query(Room).all()]

@app.get("/teachers/free")
def free_teachers(day:str,start_time:time,end_time:time,db:Session=Depends(get_db),user=Depends(current_user)):
    rows=[]
    for t in db.query(Teacher).all():
        busy=False
        for l in db.query(Lecture).filter(Lecture.teacher_id==t.id,Lecture.day_of_week==day.upper()).all():
            if l.start_time < end_time and start_time < l.end_time: busy=True; break
        if not busy:
            from .models import User
            rows.append({"id":t.id,"name":db.get(User,t.user_id).name})
    return rows

@app.get("/rooms/free")
def free_rooms(day:str,start_time:time,end_time:time,db:Session=Depends(get_db),user=Depends(current_user)):
    rows=[]
    for r in db.query(Room).all():
        busy=False
        for l in db.query(Lecture).filter(Lecture.room_id==r.id,Lecture.day_of_week==day.upper()).all():
            if l.start_time < end_time and start_time < l.end_time: busy=True; break
        if not busy: rows.append({"id":r.id,"room_number":r.room_number})
    return rows

@app.get("/search")
def search(q:str=Query(min_length=1),db:Session=Depends(get_db),user=Depends(current_user)):
    from .models import User, Subject, ClassRoomGroup, Room
    ql=f"%{q.lower()}%"
    result=[]
    for l in db.query(Lecture).all():
        t=db.get(Teacher,l.teacher_id); u=db.get(User,t.user_id); c=db.get(ClassRoomGroup,l.class_id); s=db.get(Subject,l.subject_id); r=db.get(Room,l.room_id)
        text=" ".join([u.name,c.name,c.section,s.name,s.code,r.room_number]).lower()
        if q.lower() in text:
            result.append(lecture_payload(db,l))
    return result

@app.post("/timetable/import")
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_role(Role.ADMIN)),
):
    """Import a timetable CSV and atomically replace the current lecture schedule."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")

    raw = await file.read()
    try:
        file_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            file_text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise HTTPException(400, "CSV must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(file_text))
    headers = {h.strip().lower() for h in (reader.fieldnames or []) if h}
    canonical = {"day", "start_time", "end_time", "class", "section", "subject_code", "subject", "teacher", "room"}
    friendly = {"day", "start_time", "end_time", "subject", "faculty", "room", "section", "semester"}
    if not headers:
        raise HTTPException(400, "CSV file is empty or has no header row.")
    if not (canonical.issubset(headers) or friendly.issubset(headers)):
        raise HTTPException(400, "Unsupported CSV format. Use either the standard timetable columns or: day,start_time,end_time,subject,faculty,room,section,semester")

    field_map = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
    rows = list(reader)
    parsed = []
    errors = []

    def value(row, key, default=""):
        actual = field_map.get(key)
        return (row.get(actual, default) or "").strip() if actual else default

    # Validate the entire CSV before changing the database. This prevents a bad
    # upload from deleting the timetable that is currently working.
    for line, row in enumerate(rows, 2):
        try:
            day = value(row, "day").upper()
            start = time.fromisoformat(value(row, "start_time"))
            end = time.fromisoformat(value(row, "end_time"))
            if day not in {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}:
                raise ValueError(f"Invalid day: {day}")
            if start >= end:
                raise ValueError("Start time must be before end time")

            if canonical.issubset(headers):
                class_name = value(row, "class")
                section = value(row, "section")
                subject_name = value(row, "subject")
                subject_code = value(row, "subject_code")
                teacher_name = value(row, "teacher")
                room_number = value(row, "room")
                semester = value(row, "semester")
            else:
                subject_name = value(row, "subject")
                subject_code = ""
                teacher_name = value(row, "faculty")
                room_number = value(row, "room")
                semester = value(row, "semester")
                raw_section = value(row, "section").upper()
                if "-" in raw_section:
                    class_name, section = raw_section.split("-", 1)
                else:
                    class_name, section = raw_section, "A"

            if not class_name.strip() or not section.strip(): raise ValueError("Class and section are required")
            if not subject_name.strip(): raise ValueError("Subject is required")
            if not teacher_name.strip(): raise ValueError("Teacher/faculty is required")
            if not room_number.strip(): raise ValueError("Room is required")

            parsed.append({
                "line": line, "day": day, "start": start, "end": end,
                "class_name": class_name.strip(), "section": section.strip(),
                "subject_name": subject_name.strip(), "subject_code": subject_code.strip(),
                "teacher_name": teacher_name.strip(), "room_number": room_number.strip(),
                "semester": semester.strip(), "lecture_type": value(row, "lecture_type", "Lecture") or "Lecture",
            })
        except Exception as exc:
            errors.append({"line": line, "error": str(exc)})

    if errors:
        raise HTTPException(400, detail={
            "message": "CSV was not imported. Fix the invalid rows and try again.",
            "errors": errors,
        })
    if not parsed:
        raise HTTPException(400, "CSV contains no timetable rows.")

    def get_or_create_department(code):
        code=(code or "GEN").strip().upper()[:20] or "GEN"
        d=db.query(Department).filter(Department.code==code).first()
        if not d:
            d=Department(name=code,code=code); db.add(d); db.flush()
        return d

    def get_or_create_class(label, section, semester):
        label=label.strip().upper(); section=section.strip().upper()
        cls=db.query(ClassRoomGroup).filter(ClassRoomGroup.name==label,ClassRoomGroup.section==section).first()
        if not cls:
            try: sem=int(semester) if semester else 6
            except ValueError: sem=6
            cls=ClassRoomGroup(name=label,section=section,semester=sem,academic_year="2026-27",department_id=get_or_create_department(label).id)
            db.add(cls); db.flush()
        return cls

    def get_or_create_teacher(name):
        teacher=db.query(Teacher).join(User,Teacher.user_id==User.id).filter(User.name.ilike(name)).first()
        if teacher: return teacher
        dept=get_or_create_department("GEN")
        base="".join(ch.lower() if ch.isalnum() else "." for ch in name).strip(".") or "teacher"
        email=f"{base}@imported.local"; n=1
        while db.query(User).filter(User.email==email).first():
            n+=1; email=f"{base}{n}@imported.local"
        u=User(name=name,email=email,password_hash=hash_password("teacher123"),role=Role.TEACHER)
        db.add(u); db.flush()
        teacher=Teacher(user_id=u.id,employee_id=f"CSV{db.query(Teacher).count()+1:04d}",department_id=dept.id)
        db.add(teacher); db.flush()
        return teacher

    def get_or_create_subject(name,code,department):
        name=name.strip(); code=code.strip().upper()
        subject=db.query(Subject).filter(Subject.code==code).first() if code else None
        if not subject: subject=db.query(Subject).filter(Subject.name.ilike(name)).first()
        if subject: return subject
        if not code:
            import re
            base="CSV-"+re.sub(r"[^A-Z0-9]+","-",name.upper()).strip("-")[:20]
            code=base or "CSV-SUBJECT"; i=1; candidate=code
            while db.query(Subject).filter(Subject.code==candidate).first():
                i+=1; candidate=f"{code[:25]}-{i}"
            code=candidate
        subject=Subject(name=name,code=code,credits=3,department_id=department.id); db.add(subject); db.flush()
        return subject

    def get_or_create_room(number):
        room=db.query(Room).filter(Room.room_number==number).first()
        if not room:
            room=Room(room_number=number,building="Imported",capacity=60,room_type="Classroom"); db.add(room); db.flush()
        return room

    try:
        # Replace only after validation succeeded. Since this whole operation is
        # one transaction, a database error rolls back the old timetable too.
        db.query(Lecture).delete(synchronize_session=False)
        db.flush()
        created=[]
        seen=set()
        for item in parsed:
            cls=get_or_create_class(item["class_name"],item["section"],item["semester"])
            department=db.get(Department,cls.department_id)
            teacher=get_or_create_teacher(item["teacher_name"])
            subject=get_or_create_subject(item["subject_name"],item["subject_code"],department)
            room=get_or_create_room(item["room_number"])
            key=(teacher.id,cls.id,subject.id,room.id,item["day"],item["start"],item["end"])
            if key in seen:
                raise ValueError(f"Duplicate timetable row at CSV line {item['line']}")
            seen.add(key)
            data=LectureCreate(teacher_id=teacher.id,class_id=cls.id,subject_id=subject.id,room_id=room.id,day_of_week=item["day"],start_time=item["start"],end_time=item["end"],lecture_type=item["lecture_type"])
            issues=conflicts(db,data)
            if issues: raise ValueError(f"CSV line {item['line']}: {'; '.join(issues)}")
            db.add(Lecture(**{**data.model_dump(), "day_of_week": item["day"]}))
            created.append(item["line"])
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"Import failed. The previous timetable was kept. {exc}")

    return {"message":"Timetable imported successfully", "filename":file.filename, "created_lines":created, "updated_lines":[], "errors":[]}
