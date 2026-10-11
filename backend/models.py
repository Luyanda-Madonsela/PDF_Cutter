import uuid
from typing import List, Optional, Annotated
from datetime import datetime, timezone
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict

PyObjectId = Annotated[str, BeforeValidator(str)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")

    def to_mongo(self) -> dict:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)


class Part(BaseModel):
    page: int  # 0-based page index
    y0: int    # 0-1000
    y1: int


class Question(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order: int = 0
    label: str
    filename: str = ""
    storage_path: str
    parts: List[Part] = []
    pages: List[int] = []
    marks: Optional[int] = None
    width: int = 0
    height: int = 0


class JobMeta(BaseModel):
    subject: str = ""
    grade: str = ""
    year: str = ""
    session: str = ""
    paper: str = ""
    province: str = ""
    language: str = ""
    doc_type: str = "question_paper"  # question_paper | memo


class Job(BaseDocument):
    filename: str
    pdf_path: str = ""
    is_deleted: bool = False
    status: str = "queued"  # queued | processing | done | error
    total_pages: int = 0
    pages_done: int = 0
    error: Optional[str] = None
    questions: List[Question] = []
    page_paths: List[str] = []
    page_masks: List[List[List[int]]] = []  # per page: [ymin, xmin, ymax, xmax] 0-1000 boxes to white out
    meta: JobMeta = Field(default_factory=JobMeta)
    base_name: str = ""
    paired_job_id: Optional[str] = None
    forced_memo: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class QuestionUpdate(BaseModel):
    label: Optional[str] = None
    parts: Optional[List[Part]] = None
    marks: Optional[int] = None
    clear_marks: bool = False
