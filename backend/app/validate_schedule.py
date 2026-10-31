
from collections import defaultdict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Operation,
    OperationSchedule,
    MachineCalendar,
    OperationMaterialRequirement,
    InventoryLot,
    ChangeoverMatrix,
    MachineDowntime
)

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
db = Session()

errors = []
warnings = []

try:
    print("STARTING SCHEDULE VALIDATION...\n")

    schedules = (
        db.query(OperationSchedule)
        .order_by(
            OperationSchedule.machine_id,
            OperationSchedule.start_time
        )
        .all()
    )

    print("Total saved schedules:", len(schedules))

    # 1. Check machine overlaps
    machine_groups = defaultdict(list)

    for schedule in schedules:
        machine_groups[schedule.machine_id].append(schedule)

    for machine_id, machine_schedules in machine_groups.items():
        machine_schedules.sort(key=lambda s: s.start_time)

        for previous, current in zip(
            machine_schedules,
            machine_schedules[1:]
        ):
            if current.start_time < previous.end_time:
                errors.append(
                    f"Machine overlap: {previous.schedule_code} "
                    f"and {current.schedule_code}"
                )

    print("Machine overlap check: completed")


    # 2. Check machine downtime conflicts
    downtimes = db.query(MachineDowntime).all()

    downtime_groups = defaultdict(list)

    for downtime in downtimes:
        if downtime.status and downtime.status.lower() == "cancelled":
            continue

        downtime_groups[downtime.machine_id].append(downtime)

    downtime_conflict_count = 0

    for schedule in schedules:
        for downtime in downtime_groups[schedule.machine_id]:

            if (
                schedule.start_time < downtime.end_time
                and schedule.end_time > downtime.start_time
            ):
                downtime_conflict_count += 1

                print(
                    "\nDOWNTIME CONFLICT:"
                    f"\nSchedule: {schedule.schedule_code}"
                    f"\nMachine ID: {schedule.machine_id}"
                    f"\nSchedule Start: {schedule.start_time}"
                    f"\nSchedule End: {schedule.end_time}"
                    f"\nDowntime ID: {downtime.id}"
                    f"\nDowntime Start: {downtime.start_time}"
                    f"\nDowntime End: {downtime.end_time}"
                    f"\nDowntime Reason: {downtime.reason}"
                )

                errors.append(
                    f"Machine downtime conflict: "
                    f"{schedule.schedule_code} overlaps with "
                    f"downtime ID {downtime.id}"
                )

    print(
        "\nMachine downtime check completed. "
        f"Conflicts found: {downtime_conflict_count}"
    )


    # 3. Check machine shift calendars
    for schedule in schedules:
        calendars = (
            db.query(MachineCalendar)
            .filter_by(machine_id=schedule.machine_id)
            .all()
        )

        inside_shift = any(
            calendar.shift_start <= schedule.start_time
            and schedule.end_time <= calendar.shift_end
            for calendar in calendars
        )

        if not inside_shift:
            errors.append(
                f"Outside machine shift: {schedule.schedule_code}"
            )

    print("Machine calendar check: completed")

    # 4. Check operation precedence
    scheduled_by_operation = {
        schedule.operation_id: schedule
        for schedule in schedules
    }

    orders = (
        db.query(Operation)
        .order_by(
            Operation.production_order_id,
            Operation.sequence_number
        )
        .all()
    )

    operations_by_order = defaultdict(list)

    for operation in orders:
        operations_by_order[
            operation.production_order_id
        ].append(operation)

    for order_operations in operations_by_order.values():
        for previous, current in zip(
            order_operations,
            order_operations[1:]
        ):
            previous_schedule = scheduled_by_operation.get(previous.id)
            current_schedule = scheduled_by_operation.get(current.id)

            if current_schedule and not previous_schedule:
                errors.append(
                    f"Precedence violation: {current.operation_code}"
                )

            elif previous_schedule and current_schedule:
                if current_schedule.start_time < previous_schedule.end_time:
                    errors.append(
                        f"Precedence violation: {current.operation_code}"
                    )

    print("Operation precedence check: completed")

    # 5. Check material availability and total inventory
    lots = db.query(InventoryLot).all()

    lots_by_material = defaultdict(list)

    for lot in lots:
        lots_by_material[lot.material_id].append(lot)

    material_usage = defaultdict(list)

    for schedule in schedules:
        requirements = (
            db.query(OperationMaterialRequirement)
            .filter_by(operation_id=schedule.operation_id)
            .all()
        )

        for requirement in requirements:
            material_usage[requirement.material_id].append({
                "time": schedule.start_time,
                "quantity": requirement.quantity_required,
                "operation": schedule.operation.operation_code
            })

    for material_id, usages in material_usage.items():
        usages.sort(key=lambda item: item["time"])
        cumulative_usage = 0

        for usage in usages:
            cumulative_usage += usage["quantity"]

            available_quantity = sum(
                lot.quantity
                for lot in lots_by_material[material_id]
                if lot.available_at <= usage["time"]
            )

            if available_quantity < cumulative_usage:
                errors.append(
                    f"Material availability/quantity violation: "
                    f"{usage['operation']}"
                )

    print("Material availability check: completed")

    # 6. Check sequence-dependent changeover time
    changeovers = db.query(ChangeoverMatrix).all()

    changeover_lookup = {
        (
            item.machine_id,
            item.from_product_id,
            item.to_product_id
        ): item.changeover_minutes
        for item in changeovers
    }

    for machine_id, machine_schedules in machine_groups.items():
        machine_schedules.sort(key=lambda s: s.start_time)

        for previous, current in zip(
            machine_schedules,
            machine_schedules[1:]
        ):
            previous_product = (
                previous.operation.production_order.product_id
            )

            current_product = (
                current.operation.production_order.product_id
            )

            required_minutes = changeover_lookup.get(
                (machine_id, previous_product, current_product),
                0
            )

            actual_gap = (
                current.start_time - previous.end_time
            ).total_seconds() / 60

            if actual_gap < required_minutes:
                errors.append(
                    f"Changeover violation: {current.schedule_code}"
                )

    print("Changeover check: completed")

    # 7. Validation summary
    total_operations = db.query(Operation).count()
    scheduled_count = len(schedules)
    unscheduled_count = total_operations - scheduled_count

    print("\n------------------------------")
    print("SCHEDULE VALIDATION SUMMARY")
    print("------------------------------")

    print("Total operations:", total_operations)
    print("Scheduled:", scheduled_count)
    print("Unscheduled:", unscheduled_count)
    print("Total downtime records:", len(downtimes))
    print("Validation errors:", len(errors))

    if errors:
        print("\nVALIDATION FAILED")

        for error in errors[:30]:
            print("-", error)

        if len(errors) > 30:
            print("Additional errors:", len(errors) - 30)

    else:
        print("\nALL SCHEDULE VALIDATION CHECKS PASSED!")

    print("------------------------------")

except Exception as error:
    print("VALIDATION ERROR:", error)
    raise

finally:
    db.close()
