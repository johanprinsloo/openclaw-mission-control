from enum import Enum
from typing import Optional, List
from pydantic import BaseModel

class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    IN_PROGRESS = "in-progress"
    IN_REVIEW = "in-review"
    COMPLETE = "complete"

class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ProjectStage(str, Enum):
    DEFINITION = "definition"
    POC = "poc"
    DEVELOPMENT = "development"
    TESTING = "testing"
    LAUNCH = "launch"
    MAINTENANCE = "maintenance"

# Ordered list for transition validation
PROJECT_STAGE_ORDER: list["ProjectStage"] = [
    ProjectStage.DEFINITION,
    ProjectStage.POC,
    ProjectStage.DEVELOPMENT,
    ProjectStage.TESTING,
    ProjectStage.LAUNCH,
    ProjectStage.MAINTENANCE,
]

class Role(str, Enum):
    ADMIN = "administrator"
    CONTRIBUTOR = "contributor"

class EvidenceType(str, Enum):
    PR_LINK = "pr_link"
    TEST_RESULTS = "test_results"
    DOC_URL = "doc_url"

class Pagination(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int

class APIResponse(BaseModel):
    data: Optional[object] = None
    error: Optional[object] = None
