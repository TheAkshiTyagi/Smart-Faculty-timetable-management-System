from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Time, Enum, Index
from sqlalchemy.orm import relationship
from .database import Base
import enum

class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    code = Column(String(20), unique=True, nullable=False)

class ClassRoomGroup(Base):
    __tablename__ = "classes"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    section = Column(String(20), nullable=False)
    semester = Column(Integer, nullable=False)
    academic_year = Column(String(20), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)

class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    employee_id = Column(String(50), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    designation = Column(String(100), default="Assistant Professor")

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    enrollment_number = Column(String(80), unique=True, nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    code = Column(String(30), unique=True, nullable=False)
    credits = Column(Integer, default=3)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    room_number = Column(String(50), unique=True, nullable=False)
    building = Column(String(80), default="Main Block")
    capacity = Column(Integer, default=60)
    room_type = Column(String(50), default="Classroom")

class Lecture(Base):
    __tablename__ = "lectures"
    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    day_of_week = Column(String(15), nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    lecture_type = Column(String(30), default="Lecture")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Index("ix_lecture_teacher_day", Lecture.teacher_id, Lecture.day_of_week)
Index("ix_lecture_class_day", Lecture.class_id, Lecture.day_of_week)
Index("ix_lecture_room_day", Lecture.room_id, Lecture.day_of_week)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    message = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class NotificationAudience(str, enum.Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    recipient_role = Column(Enum(NotificationAudience), nullable=True, index=True)
    message = Column(String(1200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_active = Column(Boolean, default=True)
