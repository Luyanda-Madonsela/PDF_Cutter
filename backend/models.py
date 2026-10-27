import uuid
from typing import List, Optional, Annotated
from datetime import datetime, timezone
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict

PyObjectId = Annotated[str, BeforeValidator(str)]
DOC_TYPES = ("question_paper", "memo", "addendum", "errata")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    related_labels: List[str] = []
    filename: str = ""
    storage_path: str
    parts: List[Part] = []
    pages: List[int] = []
    marks: Optional[int] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None  # Easy | Medium | Hard
    erase_status: str = "none"  # none | pending | applied | rejected
    erase_applied: List[List[int]] = []  # approved boxes: [page, ymin, xmin, ymax, xmax]
    erase_manual: List[List[int]] = []  # subset of erase_applied drawn by the user
    erase_white: List[List[int]] = []  # subset of erase_applied explicitly filled with white
    memo_links: List[str] = []  # manually linked memo question IDs; empty means automatic matching
    crop_history: List[List[Part]] = []  # previous crops, newest last (for undo)
    flags: List[str] = []
    reviewed: bool = False
    annotations: List[dict] = []
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
    doc_type: str = "question_paper"
    school: str = ""  # school-set tests only
    assessment: str = ""  # Test / Control Test / Exam / Assignment / Investigation / Project
    term: str = ""  # 1-4
    curriculum: str = ""  # "" = CAPS/IEB, or cambridge / ib / nbt
    qualification: str = ""  # syllabus code, e.g. 0580, 9709, IB-MAA-HL, NBT-MAT
    variant: str = ""  # Cambridge variant 1-3 or IB time zone 0-2


class Job(BaseDocument):
    filename: str
    pdf_path: str = ""
    drive_source: Optional[dict] = None  # {file_id, paper_folder_id} when imported from Google Drive
    paused_from: Optional[str] = None  # status to resume to after a spending-limit pause
    is_deleted: bool = False
    # queued -> classifying -> waiting (set incomplete) -> ready -> processing -> done | error
    status: str = "queued"
    total_pages: int = 0
    pages_done: int = 0
    error: Optional[str] = None
    questions: List[Question] = []
    page_paths: List[str] = []
    page_masks: List[List[List[int]]] = []  # per page: [ymin, xmin, ymax, xmax] 0-1000 boxes to erase
    content_col: List[int] = []  # [x0, x1] px at render zoom
    meta: JobMeta = Field(default_factory=JobMeta)
    base_name: str = ""
    set_id: Optional[str] = None
    forced_type: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class DocSummary(BaseModel):
    job_id: str
    doc_type: str
    filename: str
    status: str
    pages_done: int = 0
    total_pages: int = 0


class PaperSet(BaseDocument):
    meta: JobMeta = Field(default_factory=JobMeta)
    base_name: str = ""
    school_test_number: Optional[int] = None
    mode: str = "bulk"  # single | bulk
    status: str = "needs_memo"  # needs_memo | needs_paper | processing | done | error
    docs: List[DocSummary] = []
    flagged: int = 0
    question_count: int = 0
    rating: Optional[dict] = None  # difficulty re-rating progress: {status, done, total, error}
    drive: Optional[dict] = None  # {status, uploaded, total, folder_url, error, at}
    is_deleted: bool = False
    created_at: str = Field(default_factory=now_iso)


class EraseDecision(BaseModel):
    boxes: List[List[int]] = []  # approved subset of proposals; empty = keep original
    manual: List[List[int]] = []  # user-drawn boxes: [page, ymin, xmin, ymax, xmax] 0-1000
    white: List[List[int]] = []  # user-drawn boxes to fill with white


class MemoLinkUpdate(BaseModel):
    memo_qids: List[str] = []


class QuestionAnnotations(BaseModel):
    annotations: List[dict] = []


class QuestionUpdate(BaseModel):
    label: Optional[str] = None
    parts: Optional[List[Part]] = None
    marks: Optional[int] = None
    clear_marks: bool = False
    topic: Optional[str] = None
    difficulty: Optional[str] = None  # "" clears it


class QuestionSplit(BaseModel):
    page: int = Field(ge=0)
    y: int = Field(ge=0, le=1000)
    label: str = Field(min_length=1)
    parts: Optional[List[Part]] = None
