from datetime import time
from sqlalchemy.orm import Session
from .models import *
from .auth import hash_password

def seed(db: Session):
    if db.query(User).count():
        return

    deps = []
    for name, code in [("Computer Science","CSE"),("Electronics","ECE"),("Information Technology","IT"),("Artificial Intelligence","AIML"),("Data Science","DS")]:
        d = Department(name=name, code=code); db.add(d); deps.append(d)
    db.flush()

    users = [
        User(name="System Administrator", email="admin@demo.com", password_hash=hash_password("admin123"), role=Role.ADMIN),
        User(name="Dr. Rajesh Sharma", email="teacher@demo.com", password_hash=hash_password("teacher123"), role=Role.TEACHER),
        User(name="Ayush Student", email="student@demo.com", password_hash=hash_password("student123"), role=Role.STUDENT),
    ]
    db.add_all(users); db.flush()

    teachers = []
    teacher_names = ["Dr. Rajesh Sharma","Prof. Amit Verma","Dr. Neha Singh","Prof. Rahul Gupta","Dr. Priya Mehta","Dr. Ankit Kumar","Prof. Ritu Jain","Dr. Mohit Agarwal"]
    for i, name in enumerate(teacher_names, 1):
        u = users[1] if i == 1 else User(name=name, email=f"teacher{i}@demo.com", password_hash=hash_password("teacher123"), role=Role.TEACHER)
        if i != 1: db.add(u); db.flush()
        teachers.append(Teacher(user_id=u.id, employee_id=f"EMP{i:03}", department_id=deps[(i-1)%5].id))
    db.add_all(teachers); db.flush()

    classes=[]
    for i, (n,s) in enumerate([("CSE","A"),("CSE","B"),("CSE","C"),("AIML","A"),("AIML","B"),("IT","A"),("ECE","A"),("DS","A")]):
        classes.append(ClassRoomGroup(name=n, section=s, semester=6, academic_year="2026-27", department_id=deps[i%5].id))
    db.add_all(classes); db.flush()

    subjects=[]
    names=[("Database Management Systems","CS301"),("Machine Learning","CS302"),("Operating Systems","CS303"),("Computer Networks","CS304"),("Java Programming","CS305"),("Artificial Intelligence","AI301"),("Data Structures","CS306"),("Software Engineering","CS307"),("Deep Learning","AI302"),("Cloud Computing","CS308")]
    for i,(n,c) in enumerate(names):
        subjects.append(Subject(name=n,code=c,credits=3,department_id=deps[i%5].id))
    db.add_all(subjects); db.flush()

    rooms=[]
    for i in range(1,11):
        rooms.append(Room(room_number=f"A-{100+i}", building="Main Block", capacity=60, room_type="Classroom"))
    rooms += [Room(room_number="LAB-1", building="Tech Block", capacity=40, room_type="Computer Lab"), Room(room_number="LAB-2", building="Tech Block", capacity=40, room_type="Computer Lab")]
    db.add_all(rooms); db.flush()

    db.add(Student(user_id=users[2].id, enrollment_number="STU2026CSE001", class_id=classes[0].id))
    db.flush()

    slots=[("MONDAY",time(9),time(10)),("MONDAY",time(10),time(11)),("MONDAY",time(11),time(12)),
           ("TUESDAY",time(9),time(10)),("TUESDAY",time(10),time(11)),("TUESDAY",time(11),time(12)),
           ("WEDNESDAY",time(9),time(10)),("WEDNESDAY",time(10),time(11)),("THURSDAY",time(9),time(10)),
           ("FRIDAY",time(10),time(11)),("FRIDAY",time(11),time(12)),("SATURDAY",time(9),time(10))]
    # Create conflict-free sample lectures by distributing teachers/classes/rooms.
    for i,(day,st,en) in enumerate(slots):
        db.add(Lecture(
            teacher_id=teachers[i%len(teachers)].id,
            class_id=classes[i%len(classes)].id,
            subject_id=subjects[i%len(subjects)].id,
            room_id=rooms[i%len(rooms)].id,
            day_of_week=day,start_time=st,end_time=en,lecture_type="Lecture"
        ))
    db.commit()
