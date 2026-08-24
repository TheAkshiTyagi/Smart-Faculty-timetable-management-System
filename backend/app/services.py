from datetime import time
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .models import Lecture, Teacher, ClassRoomGroup, Room

def overlap(a_start: time, a_end: time, b_start: time, b_end: time):
    return a_start < b_end and b_start < a_end

def conflicts(db: Session, data, exclude_id=None):
    q = db.query(Lecture).filter(Lecture.day_of_week == data.day_of_week.upper())
    if exclude_id:
        q = q.filter(Lecture.id != exclude_id)
    rows = q.all()
    issues = []
    for row in rows:
        if not overlap(data.start_time, data.end_time, row.start_time, row.end_time):
            continue
        if row.teacher_id == data.teacher_id:
            issues.append("Teacher already has a lecture during this time.")
        if row.class_id == data.class_id:
            issues.append("Class already has a lecture during this time.")
        if row.room_id == data.room_id:
            issues.append("Room is already occupied during this time.")
    return sorted(set(issues))

def lecture_payload(db, row):
    teacher = db.get(Teacher, row.teacher_id)
    cls = db.get(ClassRoomGroup, row.class_id)
    room = db.get(Room, row.room_id)
    from .models import Subject, User
    subject = db.get(Subject, row.subject_id)
    user = db.get(User, teacher.user_id) if teacher else None
    return {
        "id": row.id, "teacher_name": user.name if user else "",
        "class_name": f"{cls.name}-{cls.section}" if cls else "",
        "subject_name": subject.name if subject else "",
        "room_number": room.room_number if room else "",
        "day_of_week": row.day_of_week,
        "start_time": row.start_time.strftime("%H:%M"),
        "end_time": row.end_time.strftime("%H:%M"),
    }
