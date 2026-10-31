
from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import engine, Base, get_db
from app import models

import json
from pathlib import Path

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="YottaFlex Production Scheduler",
    description="Smart manufacturing production scheduling system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "project": "YottaFlex Production Scheduler",
        "status": "running",
        "message": "Welcome to the production scheduling system"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "database": "SQLite connected"
    }


@app.get("/analytics")
def get_analytics():

    analytics_file = Path("../data/analytics.json")

    if not analytics_file.exists():
        return {
            "error": "Analytics file not found. Run analytics first."
        }

    with open(analytics_file, "r", encoding="utf-8") as file:
        analytics = json.load(file)

    return analytics



@app.get("/orders")
def get_orders(db: Session = Depends(get_db)):

    orders = (
        db.query(models.ProductionOrder)
        .options(joinedload(models.ProductionOrder.product))
        .order_by(models.ProductionOrder.id)
        .all()
    )

    results = []

    for order in orders:

        total_operations = (
            db.query(func.count(models.Operation.id))
            .filter(
                models.Operation.production_order_id == order.id
            )
            .scalar()
        )

        scheduled_operations = (
            db.query(func.count(models.OperationSchedule.id))
            .join(
                models.Operation,
                models.OperationSchedule.operation_id == models.Operation.id
            )
            .filter(
                models.Operation.production_order_id == order.id
            )
            .scalar()
        )

        if total_operations == 0:
            scheduling_status = "No Operations"
        elif scheduled_operations == total_operations:
            scheduling_status = "Scheduled"
        elif scheduled_operations > 0:
            scheduling_status = "Partially Scheduled"
        else:
            scheduling_status = "Unscheduled"

        results.append({
            "id": order.id,
            "order_code": order.order_code,
            "product_name": order.product.name,
            "quantity": order.quantity,
            "priority": order.priority,
            "due_date": order.due_date.isoformat(),
            "status": scheduling_status,
            "total_operations": total_operations,
            "scheduled_operations": scheduled_operations,
            "unscheduled_operations": (
                total_operations - scheduled_operations
            )
        })

    return results


@app.get("/unscheduled")
def get_unscheduled_events(
  limit: int = Query(default=2000, ge=1, le=2000),
    db: Session = Depends(get_db)
):

    events = (
        db.query(models.ScheduleEvent)
        .filter(
            models.ScheduleEvent.event_type == "OPERATION_UNSCHEDULED"
        )
        .order_by(models.ScheduleEvent.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []

    for event in events:
        description = event.description or ""

        reason = "UNKNOWN"

        if ": " in description:
            reason_part = description.split(": ", 1)[1]
            reason = reason_part.split(" - ", 1)[0]

        results.append({
            "event_id": event.id,
            "event_type": event.event_type,
            "description": description,
            "reason": reason,
            "created_at": (
                event.created_at.isoformat()
                if event.created_at else None
            )
        })

    return {
        "total_returned": len(results),
        "events": results
    }



@app.get("/schedule")
def get_production_schedule(
    machine_id: int | None = None,
    order_id: int | None = None,
    limit: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db)
):
    query = (
        db.query(models.OperationSchedule)
        .options(
            joinedload(models.OperationSchedule.machine),
            joinedload(models.OperationSchedule.operation)
            .joinedload(models.Operation.production_order)
            .joinedload(models.ProductionOrder.product),
            joinedload(models.OperationSchedule.operation)
            .joinedload(models.Operation.routing_step)
        )
    )

    if machine_id is not None:
        query = query.filter(
            models.OperationSchedule.machine_id == machine_id
        )

    if order_id is not None:
        query = query.filter(
            models.OperationSchedule.operation.has(
                production_order_id=order_id
            )
        )

    schedules = (
        query
        .order_by(models.OperationSchedule.start_time)
        .limit(limit)
        .all()
    )

    results = []

    for schedule in schedules:
        operation = schedule.operation
        order = operation.production_order

        duration = int(
            (schedule.end_time - schedule.start_time).total_seconds() / 60
        )

        results.append({
            "schedule_id": schedule.id,
            "schedule_code": schedule.schedule_code,
            "operation_id": operation.operation_code,
            "operation_name": operation.routing_step.operation_name,
            "order_id": order.order_code,
            "product_name": order.product.name,
            "quantity": order.quantity,
            "priority": order.priority,
            "machine_id": schedule.machine.id,
            "machine_code": schedule.machine.machine_code,
            "machine_name": schedule.machine.name,
            "start_time": schedule.start_time.isoformat(),
            "end_time": schedule.end_time.isoformat(),
            "duration_minutes": duration,
            "status": schedule.status
        })

    return {
        "total_returned": len(results),
        "schedules": results
    }
