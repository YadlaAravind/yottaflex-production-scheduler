
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    ProductionOrder,
    Operation,
    OperationSchedule,
    OperationMaterialRequirement,
    InventoryLot,
    MachineCalendar,
    MachineDowntime,
    ChangeoverMatrix,
    ScheduleEvent,
)

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)


def record_unscheduled_event(db, operation, reason, details=""):
    event = ScheduleEvent(
        operation_schedule_id=None,
        event_type="OPERATION_UNSCHEDULED",
        description=(
            f"{operation.operation_code}: {reason} - {details}"
        )[:255]
    )
    db.add(event)


def run_scheduler():
    db = Session()

    try:
        print("STARTING PRODUCTION SCHEDULER...\n")

        existing_schedules = db.query(OperationSchedule).all()

        scheduled_operation_ids = {
            schedule.operation_id
            for schedule in existing_schedules
        }

        machine_bookings = {}

        for schedule in existing_schedules:
            product_id = schedule.operation.production_order.product_id

            machine_bookings.setdefault(schedule.machine_id, []).append({
                "start": schedule.start_time,
                "end": schedule.end_time,
                "product_id": product_id
            })

        downtime_records = db.query(MachineDowntime).all()
        downtime_by_machine = {}

        for downtime in downtime_records:
            downtime_by_machine.setdefault(
                downtime.machine_id, []
            ).append({
                "start": downtime.start_time,
                "end": downtime.end_time
            })

        inventory_lots = db.query(InventoryLot).all()

        remaining_inventory = {
            lot.id: lot.quantity for lot in inventory_lots
        }

        lots_by_material = {}

        for lot in inventory_lots:
            lots_by_material.setdefault(
                lot.material_id, []
            ).append(lot)

        for lots in lots_by_material.values():
            lots.sort(key=lambda lot: lot.available_at)

        changeovers = db.query(ChangeoverMatrix).all()
        changeover_lookup = {}

        for item in changeovers:
            changeover_lookup[
                (
                    item.machine_id,
                    item.from_product_id,
                    item.to_product_id
                )
            ] = item.changeover_minutes

        orders = db.query(ProductionOrder).all()

        priority_rank = {
            "urgent": 1,
            "high": 2,
            "normal": 3,
            "low": 4
        }

        orders.sort(
            key=lambda order: (
                priority_rank.get(order.priority.lower(), 5),
                order.due_date
            )
        )

        total_scheduled = 0
        total_unscheduled = 0

        unscheduled_reasons = {
            "NO_ELIGIBLE_MACHINE": 0,
            "MATERIAL_UNAVAILABLE": 0,
            "NO_AVAILABLE_SLOT": 0,
            "PREVIOUS_OPERATION_FAILED": 0
        }

        for order in orders:

            operations = (
                db.query(Operation)
                .filter_by(production_order_id=order.id)
                .order_by(Operation.sequence_number)
                .all()
            )

            previous_end = None
            previous_operation_failed = False

            for operation in operations:

                if operation.id in scheduled_operation_ids:
                    previous_schedule = (
                        db.query(OperationSchedule)
                        .filter_by(operation_id=operation.id)
                        .first()
                    )
                    previous_end = previous_schedule.end_time
                    continue

                if previous_operation_failed:
                    reason = "PREVIOUS_OPERATION_FAILED"

                    record_unscheduled_event(
                        db, operation, reason,
                        "A preceding operation could not be scheduled"
                    )

                    unscheduled_reasons[reason] += 1
                    total_unscheduled += 1
                    continue

                step = operation.routing_step
                eligible_machines = step.eligible_machines

                if not eligible_machines:
                    reason = "NO_ELIGIBLE_MACHINE"

                    record_unscheduled_event(
                        db, operation, reason,
                        "No eligible machine configured for routing step"
                    )

                    unscheduled_reasons[reason] += 1
                    total_unscheduled += 1
                    previous_operation_failed = True
                    continue

                requirements = (
                    db.query(OperationMaterialRequirement)
                    .filter_by(operation_id=operation.id)
                    .all()
                )

                selected_lots = []
                material_ready_time = None
                material_missing = False

                for requirement in requirements:

                    possible_lots = lots_by_material.get(
                        requirement.material_id, []
                    )

                    selected_lot = next(
                        (
                            lot for lot in possible_lots
                            if remaining_inventory[lot.id]
                            >= requirement.quantity_required
                            and lot.available_at is not None
                        ),
                        None
                    )

                    if selected_lot is None:
                        material_missing = True
                        break

                    selected_lots.append(
                        (selected_lot, requirement.quantity_required)
                    )

                    if (
                        material_ready_time is None
                        or selected_lot.available_at > material_ready_time
                    ):
                        material_ready_time = selected_lot.available_at

                if material_missing:
                    reason = "MATERIAL_UNAVAILABLE"

                    record_unscheduled_event(
                        db, operation, reason,
                        "Required material quantity is unavailable"
                    )

                    unscheduled_reasons[reason] += 1
                    total_unscheduled += 1
                    previous_operation_failed = True
                    continue

                duration = operation.planned_duration_minutes
                best_slot = None

                for machine in eligible_machines:

                    calendars = (
                        db.query(MachineCalendar)
                        .filter_by(machine_id=machine.id)
                        .order_by(MachineCalendar.shift_start)
                        .all()
                    )

                    bookings = machine_bookings.get(machine.id, [])
                    downtimes = downtime_by_machine.get(machine.id, [])

                    for calendar in calendars:

                        if duration > calendar.available_minutes:
                            continue

                        start = calendar.shift_start

                        if previous_end and previous_end > start:
                            start = previous_end

                        if (
                            material_ready_time
                            and material_ready_time > start
                        ):
                            start = material_ready_time

                        for attempt in range(100):

                            previous_booking = [
                                booking for booking in bookings
                                if booking["end"] <= start
                            ]

                            changeover_minutes = 0

                            if previous_booking:
                                last_booking = max(
                                    previous_booking,
                                    key=lambda booking: booking["end"]
                                )

                                changeover_minutes = changeover_lookup.get(
                                    (
                                        machine.id,
                                        last_booking["product_id"],
                                        order.product_id
                                    ),
                                    0
                                )

                                setup_start = max(
                                    start,
                                    last_booking["end"]
                                )

                                candidate_start = (
                                    setup_start
                                    + timedelta(minutes=changeover_minutes)
                                )
                            else:
                                candidate_start = start

                            candidate_end = (
                                candidate_start
                                + timedelta(minutes=duration)
                            )

                            if candidate_end > calendar.shift_end:
                                break

                            conflicts = [
                                booking for booking in bookings + downtimes
                                if (
                                    candidate_start < booking["end"]
                                    and candidate_end > booking["start"]
                                )
                            ]

                            if conflicts:
                                start = min(
                                    conflict["end"]
                                    for conflict in conflicts
                                )
                                continue

                            best_slot = {
                                "machine": machine,
                                "start": candidate_start,
                                "end": candidate_end
                            }
                            break

                        if best_slot:
                            break

                    if best_slot:
                        break

                if best_slot is None:
                    reason = "NO_AVAILABLE_SLOT"

                    record_unscheduled_event(
                        db, operation, reason,
                        "No suitable machine time slot was found"
                    )

                    unscheduled_reasons[reason] += 1
                    total_unscheduled += 1
                    previous_operation_failed = True
                    continue

                schedule_number = (
                    db.query(OperationSchedule).count() + 1
                )

                schedule = OperationSchedule(
                    schedule_code=(
                        f"SCH-{best_slot['start'].year}-"
                        f"{schedule_number:06d}"
                    ),
                    operation_id=operation.id,
                    machine_id=best_slot["machine"].id,
                    start_time=best_slot["start"],
                    end_time=best_slot["end"],
                    status="scheduled"
                )

                db.add(schedule)
                db.flush()

                event = ScheduleEvent(
                    operation_schedule_id=schedule.id,
                    event_type="SCHEDULE_CREATED",
                    description=(
                        f"{operation.operation_code} assigned to "
                        f"{best_slot['machine'].machine_code}"
                    )
                )

                db.add(event)

                for lot, quantity in selected_lots:
                    remaining_inventory[lot.id] -= quantity

                machine_bookings.setdefault(
                    best_slot["machine"].id, []
                ).append({
                    "start": best_slot["start"],
                    "end": best_slot["end"],
                    "product_id": order.product_id
                })

                previous_end = best_slot["end"]
                scheduled_operation_ids.add(operation.id)
                total_scheduled += 1

        db.commit()

        print("\nSCHEDULING COMPLETED!")
        print("New operations scheduled:", total_scheduled)
        print("Operations not scheduled:", total_unscheduled)

        print("\nUNSCHEDULED REASONS:")

        for reason, count in unscheduled_reasons.items():
            print(f"{reason}: {count}")

        total_operations = db.query(Operation).count()
        total_schedules = db.query(OperationSchedule).count()

        print("\nTotal operations:", total_operations)
        print("Total saved schedules:", total_schedules)

        saved_events = (
            db.query(ScheduleEvent)
            .filter_by(event_type="OPERATION_UNSCHEDULED")
            .count()
        )

        print("Saved unscheduled events:", saved_events)

    except Exception as error:
        db.rollback()
        print("SCHEDULER ERROR:", error)
        raise

    finally:
        db.close()


if __name__ == "__main__":
    run_scheduler()
