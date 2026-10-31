
import csv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import OperationSchedule, MachineDowntime

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
db = Session()

conflicts = []

try:
    schedules = db.query(OperationSchedule).all()
    downtimes = db.query(MachineDowntime).all()

    for schedule in schedules:
        for downtime in downtimes:

            if downtime.machine_id != schedule.machine_id:
                continue

            if downtime.status and downtime.status.lower() == "cancelled":
                continue

            if (
                schedule.start_time < downtime.end_time
                and schedule.end_time > downtime.start_time
            ):
                conflicts.append({
                    "schedule_code": schedule.schedule_code,
                    "operation_id": schedule.operation_id,
                    "machine_id": schedule.machine_id,
                    "schedule_start": schedule.start_time,
                    "schedule_end": schedule.end_time,
                    "downtime_id": downtime.id,
                    "downtime_start": downtime.start_time,
                    "downtime_end": downtime.end_time,
                    "downtime_reason": downtime.reason
                })

    with open(
        "../data/downtime_conflicts.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=conflicts[0].keys() if conflicts else [
                "schedule_code", "operation_id", "machine_id",
                "schedule_start", "schedule_end", "downtime_id",
                "downtime_start", "downtime_end", "downtime_reason"
            ]
        )

        writer.writeheader()
        writer.writerows(conflicts)

    print("Total downtime conflicts:", len(conflicts))
    print("Exported to data/downtime_conflicts.csv")

finally:
    db.close()
