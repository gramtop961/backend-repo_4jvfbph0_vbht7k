"""
Database Schemas for Test Automation Reporting

Each Pydantic model represents a MongoDB collection. The collection name is
the lowercase of the class name. Example: TestRun -> "testrun".

These models are used for request/response validation and documentation.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# Core domain models

class TestRun(BaseModel):
    name: str = Field(..., description="Run name, e.g., Nightly Regression")
    environment: Optional[str] = Field(None, description="Environment like dev/stage/prod")
    branch: Optional[str] = Field(None, description="Git branch or version")
    build: Optional[str] = Field(None, description="Build number or commit sha")
    status: Literal["running", "passed", "failed", "skipped", "blocked"] = Field(
        "running", description="Overall execution status"
    )
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    finished_at: Optional[datetime] = Field(None, description="Finish timestamp")
    duration_ms: Optional[int] = Field(None, ge=0, description="Total duration in ms")
    total: int = Field(0, ge=0, description="Total test count")
    passed: int = Field(0, ge=0)
    failed: int = Field(0, ge=0)
    skipped: int = Field(0, ge=0)
    blocked: int = Field(0, ge=0)
    platform: Optional[str] = Field(None, description="Execution platform info")
    tags: List[str] = Field(default_factory=list, description="Labels/tags")

class TestSuite(BaseModel):
    run_id: str = Field(..., description="Associated TestRun id")
    name: str
    status: Literal["running", "passed", "failed", "skipped", "blocked"] = "running"
    duration_ms: Optional[int] = Field(None, ge=0)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    order: Optional[int] = None

class TestCase(BaseModel):
    run_id: str
    suite_id: str
    name: str
    class_name: Optional[str] = None
    status: Literal["running", "passed", "failed", "skipped", "blocked"] = "running"
    duration_ms: Optional[int] = Field(None, ge=0)
    error_message: Optional[str] = None
    error_trace: Optional[str] = None
    retries: int = 0
    category: Optional[str] = None
    author: Optional[str] = None

class LogEntry(BaseModel):
    run_id: str
    case_id: str
    level: Literal["INFO", "WARN", "ERROR", "DEBUG", "STEP"] = "INFO"
    message: str
    timestamp: Optional[datetime] = None
    step: Optional[str] = None
    attachment_url: Optional[str] = None

# Convenience ingestion payloads

class IngestCase(BaseModel):
    name: str
    class_name: Optional[str] = None
    status: Literal["running", "passed", "failed", "skipped", "blocked"]
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    error_trace: Optional[str] = None
    retries: int = 0
    category: Optional[str] = None
    author: Optional[str] = None
    logs: List[LogEntry] = Field(default_factory=list)

class IngestSuite(BaseModel):
    name: str
    status: Literal["running", "passed", "failed", "skipped", "blocked"]
    duration_ms: Optional[int] = None
    total: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    skipped: Optional[int] = None
    order: Optional[int] = None
    cases: List[IngestCase] = Field(default_factory=list)

class IngestRun(BaseModel):
    name: str
    environment: Optional[str] = None
    branch: Optional[str] = None
    build: Optional[str] = None
    status: Literal["running", "passed", "failed", "skipped", "blocked"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    platform: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    suites: List[IngestSuite] = Field(default_factory=list)
