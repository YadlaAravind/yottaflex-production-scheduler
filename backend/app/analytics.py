
import json
from pathlib import Path
from collections import defaultdict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Operation,
    OperationSchedule,
    ProductionOrder,
    MachineCalendar
)

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)


def generate_analytics():
    db = Session()

    try:
        print("GENERATING PRODUCTION ANALYTICS...\n")

        operations = db.query(Operation).all()
        schedules = db.query(OperationSchedule).all()
        orders = db.query(ProductionOrder).all()
        calendars = db.query(MachineCalendar).all()

        total_operations = len(operations)
        scheduled_count = len(schedules)
        unscheduled_count = total_operations - scheduled_count

        completion_percentage = (
            scheduled_count / total_operations * 100
            if total_operations else 0
        )

        # Calculate makespan
        if schedules:
            earliest_start = min(
                schedule.start_time for schedule in schedules
            )

            latest_end = max(
                schedule.end_time for schedule in schedules
            )

            makespan_hours = (
                latest_end - earliest_start
            ).total_seconds() / 3600
        else:
            makespan_hours = 0

        # Calculate machine utilization
        machine_busy_minutes = defaultdict(float)

        for schedule in schedules:
            duration = (
                schedule.end_time - schedule.start_time
            ).total_seconds() / 60

            machine_busy_minutes[schedule.machine_id] += duration

        machine_available_minutes = defaultdict(float)

        for calendar in calendars:
            machine_available_minutes[
                calendar.machine_id
            ] += calendar.available_minutes

        machine_utilization = {}

        for machine_id, available in machine_available_minutes.items():
            busy = machine_busy_minutes[machine_id]

            utilization = (
                busy / available * 100
                if available > 0 else 0
            )

            machine_utilization[str(machine_id)] = round(
                utilization, 2
            )

        total_available = sum(machine_available_minutes.values())
        total_busy = sum(machine_busy_minutes.values())

        overall_utilization = (
            total_busy / total_available * 100
            if total_available else 0
        )

        # Analyze order completion and lateness
        schedules_by_order = defaultdict(list)

        for schedule in schedules:
            order_id = schedule.operation.production_order_id
            schedules_by_order[order_id].append(schedule)

        late_orders = 0
        completed_orders = 0
        total_delay_hours = 0

        for order in orders:
            order_operations = [
                operation for operation in operations
                if operation.production_order_id == order.id
            ]

            order_schedules = schedules_by_order[order.id]

            # An order is fully scheduled only if all its operations
            # have a saved schedule.
            if (
                order_operations
                and len(order_schedules) == len(order_operations)
            ):
                completed_orders += 1

                final_end = max(
                    schedule.end_time
                    for schedule in order_schedules
                )

                if final_end > order.due_date:
                    late_orders += 1

                    delay = (
                        final_end - order.due_date
                    ).total_seconds() / 3600

                    total_delay_hours += delay

        average_delay_hours = (
            total_delay_hours / late_orders
            if late_orders else 0
        )

        # Prepare analytics result
        results = {
            "total_operations": total_operations,
            "scheduled_operations": scheduled_count,
            "unscheduled_operations": unscheduled_count,
            "scheduling_completion_percentage": round(
                completion_percentage, 2
            ),
            "makespan_hours": round(makespan_hours, 2),
            "overall_machine_utilization_percentage": round(
                overall_utilization, 2
            ),
            "completed_orders": completed_orders,
            "late_orders": late_orders,
            "average_delay_hours": round(
                average_delay_hours, 2
            ),
            "machine_utilization": machine_utilization
        }

        # Save analytics JSON
        output_dir = Path("../data")
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / "analytics.json"

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(results, file, indent=4)

        # Display results
        print("------------------------------")
        print("PRODUCTION ANALYTICS")
        print("------------------------------")

        for key, value in results.items():
            if key != "machine_utilization":
                print(f"{key}: {value}")

        print("\nMachine utilization:")
        for machine_id, utilization in machine_utilization.items():
            print(f"Machine {machine_id}: {utilization}%")

        print("\nAnalytics saved to:", output_file)
        print("------------------------------")

    except Exception as error:
        print("ANALYTICS ERROR:", error)
        raise

    finally:
        db.close()


if __name__ == "__main__":
    generate_analytics()
