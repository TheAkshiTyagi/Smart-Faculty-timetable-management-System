from datetime import time
from pydantic import BaseModel, EmailStr, ConfigDict
from enum import Enum

class Role(str, Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class Login(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    model_config = ConfigDict(from_attributes=True)

class LectureCreate(BaseModel):
    teacher_id: int
    class_id: int
    subject_id: int
    room_id: int
    day_of_week: str
    start_time: time
    end_time: time
    lecture_type: str = "Lecture"

class LectureOut(LectureCreate):
    id: int
    teacher_name: str = ""
    class_name: str = ""
    subject_name: str = ""
    room_number: str = ""
    model_config = ConfigDict(from_attributes=True)

class SearchResult(BaseModel):
    id: int
    teacher_name: str
    class_name: str
    subject_name: str
    room_number: str
    day_of_week: str
    start_time: str
    end_time: str


class Register(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Role
    class_id: int | None = None
    enrollment_number: str | None = None
    employee_id: str | None = None
    designation: str | None = None

class FeedbackCreate(BaseModel):
    rating: int
    message: str


class TeacherNoteCreate(BaseModel):
    audience: list[Role]
    message: str
