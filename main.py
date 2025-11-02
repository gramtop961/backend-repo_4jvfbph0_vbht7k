import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import TestRun, TestSuite, TestCase, LogEntry, IngestRun, IngestSuite, IngestCase

app = FastAPI(title="Test Automation Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utilities
class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        try:
            return str(ObjectId(str(v)))
        except Exception:
            raise ValueError("Invalid ObjectId")

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@app.get("/")
def read_root():
    return {"message": "Test Automation Report Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"
    return response


# Runs
@app.post("/api/runs")
def create_run(run: TestRun):
    data = run.model_dump()
    now = datetime.now(timezone.utc)
    if not data.get("started_at"):
        data["started_at"] = now
    inserted_id = create_document("testrun", data)
    return {"id": inserted_id}


@app.get("/api/runs")
def list_runs(limit: int = 50, status: Optional[str] = None, tag: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if status:
        filt["status"] = status
    if tag:
        filt["tags"] = tag
    runs = db["testrun"].find(filt).sort("started_at", -1).limit(int(limit))
    return [serialize_doc(r) for r in runs]


@app.get("/api/runs/{run_id}")
def get_run_detail(run_id: str):
    run = db["testrun"].find_one({"_id": to_object_id(run_id)})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    suites = list(db["testsuite"].find({"run_id": run_id}).sort("order", 1))
    for s in suites:
        s["cases"] = list(db["testcase"].find({"suite_id": str(s["_id"]) }))
        for c in s["cases"]:
            c["logs"] = list(db["logentry"].find({"case_id": str(c["_id"]) }).sort("timestamp", 1))
    result = serialize_doc(run)
    result["suites"] = [serialize_doc(serialize_doc_suite(s)) for s in suites]
    return result


def serialize_doc_suite(s: Dict[str, Any]) -> Dict[str, Any]:
    s = serialize_doc(s)
    if "cases" in s:
        s["cases"] = [serialize_doc(c) for c in s["cases"]]
        for c in s["cases"]:
            if "logs" in c:
                c["logs"] = [serialize_doc(l) for l in c["logs"]]
    return s


class RunFinishPayload(BaseModel):
    status: Optional[str] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    skipped: Optional[int] = None
    blocked: Optional[int] = None


@app.patch("/api/runs/{run_id}/finish")
def finish_run(run_id: str, payload: RunFinishPayload):
    update: Dict[str, Any] = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "finished_at" not in update:
        update["finished_at"] = datetime.now(timezone.utc)
    db["testrun"].update_one({"_id": to_object_id(run_id)}, {"$set": update})
    run = db["testrun"].find_one({"_id": to_object_id(run_id)})
    return serialize_doc(run)


# Suites
@app.post("/api/runs/{run_id}/suites")
def create_suite(run_id: str, suite: TestSuite):
    if suite.run_id != run_id:
        raise HTTPException(status_code=400, detail="run_id mismatch")
    data = suite.model_dump()
    inserted_id = create_document("testsuite", data)
    return {"id": inserted_id}


# Cases
@app.post("/api/suites/{suite_id}/cases")
def create_case(suite_id: str, case: TestCase):
    if case.suite_id != suite_id:
        raise HTTPException(status_code=400, detail="suite_id mismatch")
    data = case.model_dump()
    inserted_id = create_document("testcase", data)
    return {"id": inserted_id}


# Logs
@app.post("/api/cases/{case_id}/logs")
def add_log(case_id: str, log: LogEntry):
    if log.case_id != case_id:
        raise HTTPException(status_code=400, detail="case_id mismatch")
    data = log.model_dump()
    if not data.get("timestamp"):
        data["timestamp"] = datetime.now(timezone.utc)
    inserted_id = create_document("logentry", data)
    return {"id": inserted_id}


# Ingestion endpoint for nested payloads (run + suites + cases + logs)
@app.post("/api/ingest")
def ingest(payload: IngestRun):
    # Insert run
    run_data = TestRun(
        name=payload.name,
        environment=payload.environment,
        branch=payload.branch,
        build=payload.build,
        status=payload.status,
        started_at=payload.started_at or datetime.now(timezone.utc),
        finished_at=payload.finished_at,
        duration_ms=payload.duration_ms,
        platform=payload.platform,
        tags=payload.tags,
    ).model_dump()
    run_id = create_document("testrun", run_data)

    total = passed = failed = skipped = blocked = 0

    # Suites and cases
    for order, s in enumerate(payload.suites or []):
        suite_data = TestSuite(
            run_id=run_id,
            name=s.name,
            status=s.status,
            duration_ms=s.duration_ms,
            total=s.total or 0,
            passed=s.passed or 0,
            failed=s.failed or 0,
            skipped=s.skipped or 0,
            order=s.order if s.order is not None else order,
        ).model_dump()
        suite_id = create_document("testsuite", suite_data)

        total += suite_data["total"]
        passed += suite_data["passed"]
        failed += suite_data["failed"]
        skipped += suite_data["skipped"]
        blocked += 0

        for c in s.cases or []:
            case_data = TestCase(
                run_id=run_id,
                suite_id=suite_id,
                name=c.name,
                class_name=c.class_name,
                status=c.status,
                duration_ms=c.duration_ms,
                error_message=c.error_message,
                error_trace=c.error_trace,
                retries=c.retries,
                category=c.category,
                author=c.author,
            ).model_dump()
            case_id = create_document("testcase", case_data)
            # logs
            for l in c.logs or []:
                log_data = LogEntry(
                    run_id=run_id,
                    case_id=case_id,
                    level=l.level,
                    message=l.message,
                    timestamp=l.timestamp or datetime.now(timezone.utc),
                    step=l.step,
                    attachment_url=l.attachment_url,
                ).model_dump()
                create_document("logentry", log_data)

    # Update run aggregates
    db["testrun"].update_one(
        {"_id": to_object_id(run_id)},
        {
            "$set": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "blocked": blocked,
            }
        },
    )

    return {"id": run_id}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
