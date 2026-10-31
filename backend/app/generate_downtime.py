import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Machine, MachineDowntime

SEED = 20261022
random.seed(SEED)


def generate_downtime():
    db: Session = SessionLocal()

    try:
        machines = db.query(Machine).order_by(Machine.id).all()

        if not machines:
            print("No machines found!")
            return

        existing = db.query(MachineDowntime).count()

        if existing > 0:
            print(f"Downtime records already exist: {existing}")
            print("Skipping generation to avoid duplicates.")
            return

        base_date = datetime(2026, 11, 1, 8, 0)

        reasons = [
            "Preventive Maintenance",
            "Machine Breakdown",
            "Tool Replacement",
            "Electrical Maintenance",
            "Quality Inspection",
        ]

        records = []

        for machine in machines:
            for _ in range(2):
                start_time = base_date + timedelta(
                    days=random.randint(1, 10),
                    hours=random.randint(0, 7),
                )

                duration = random.randint(1, 4)

                records.append(
                    MachineDowntime(
                        machine_id=machine.id,
                        start_time=start_time,
                        end_time=start_time + timedelta(hours=duration),
                        reason=random.choice(reasons),
                        status="planned",
                    )
                )

        db.add_all(records)
        db.commit()

        print(f"Successfully generated {len(records)} downtime records!")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    generate_downtime()