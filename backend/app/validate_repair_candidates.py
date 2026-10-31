
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Operation,
    OperationSchedule,
    Machine,
    MachineDowntime,
    MachineCalendar,
    InventoryLot,
    OperationMaterialRequirement,
    ChangeoverMatrix,
)

# BACKUP DATABASE ONLY - READ ONLY
DATABASE_URL = "sqlite:///./yottaflex_generated_backup.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

Session = sessionmaker(bind=engine)
db = Session()


def active(record):
    return (
        not record.status
        or record.status.lower() not in ("cancelled", "canceled")
    )


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


def check_materials(operation, candidate_start, inventory_lots):
    requirements = (
        db.query(OperationMaterialRequirement)
        .filter_by(operation_id=operation.id)
        .all()
    )

    problems = []

    for req in requirements:
        suitable_lots = [
            lot for lot in inventory_lots
            if lot.material_id == req.material_id
            and lot.status
            and lot.status.lower() == "available"
            and lot.available_at <= candidate_start
            and (
                lot.expiry_at is None
                or lot.expiry_at > candidate_start
            )
            and lot.quantity >= req.quantity_required
        ]

        if not suitable_lots:
            problems.append(
                f"Material {req.material_id}: "
                f"no single eligible lot has {req.quantity_required} "
                f"{req.unit} available"
            )

    return problems


def get_changeover(
    machine_id,
    product_id,
    candidate_start,
    schedules,
    current_schedule_id,
    changeover_lookup,
):
    previous = []

    for schedule in schedules:
        if schedule.id == current_schedule_id:
            continue

        if schedule.machine_id != machine_id:
            continue

        if not active(schedule):
            continue

        if schedule.end_time <= candidate_start:
            previous.append(schedule)

    if not previous:
        return 0, None

    last_schedule = max(
        previous,
        key=lambda s: s.end_time
    )

    previous_product_id = (
        last_schedule.operation.production_order.product_id
    )

    minutes = changeover_lookup.get(
        (machine_id, previous_product_id, product_id),
        0,
    )

    return minutes, last_schedule


def find_candidate_slot(
    machine,
    calendar,
    earliest_start,
    duration,
    operation,
    current_schedule,
    schedules,
    downtimes,
    inventory_lots,
    changeover_lookup,
):
    if duration.total_seconds() / 60 > calendar.available_minutes:
        return None, "INSUFFICIENT_CALENDAR_MINUTES"

    cursor = max(calendar.shift_start, earliest_start)

    if cursor >= calendar.shift_end:
        return None, "OUTSIDE_CALENDAR"

    busy = []

    for schedule in schedules:
        if schedule.id == current_schedule.id:
            continue

        if schedule.machine_id != machine.id:
            continue

        if not active(schedule):
            continue

        busy.append((schedule.start_time, schedule.end_time))

    for downtime in downtimes:
        if downtime.machine_id != machine.id:
            continue

        if not active(downtime):
            continue

        busy.append((downtime.start_time, downtime.end_time))

    busy.sort(key=lambda item: item[0])

    product_id = operation.production_order.product_id

    for _ in range(100):

        changeover_minutes, previous_booking = get_changeover(
            machine.id,
            product_id,
            cursor,
            schedules,
            current_schedule.id,
            changeover_lookup,
        )

        setup_start = cursor

        if previous_booking:
            setup_start = max(
                cursor,
                previous_booking.end_time
            )

        candidate_start = (
            setup_start + timedelta(minutes=changeover_minutes)
        )

        candidate_end = candidate_start + duration

        if candidate_end > calendar.shift_end:
            return None, "EXCEEDS_SHIFT_END"

        conflict = next(
            (
                (busy_start, busy_end)
                for busy_start, busy_end in busy
                if overlaps(
                    candidate_start,
                    candidate_end,
                    busy_start,
                    busy_end,
                )
            ),
            None,
        )

        if conflict:
            cursor = max(cursor, conflict[1])
            continue

        material_problems = check_materials(
            operation,
            candidate_start,
            inventory_lots,
        )

        if material_problems:
            return None, "; ".join(material_problems)

        return {
            "machine": machine.machine_code,
            "machine_id": machine.id,
            "start": candidate_start,
            "end": candidate_end,
            "changeover_minutes": changeover_minutes,
        }, None

    return None, "NO_SLOT_AFTER_100_ATTEMPTS"


try:
    schedules = db.query(OperationSchedule).all()
    operations = db.query(Operation).all()
    machines = db.query(Machine).all()
    calendars = db.query(MachineCalendar).all()
    downtimes = db.query(MachineDowntime).all()
    inventory_lots = db.query(InventoryLot).all()
    changeovers = db.query(ChangeoverMatrix).all()

    active_schedules = [
        s for s in schedules if active(s)
    ]

    active_downtimes = [
        d for d in downtimes if active(d)
    ]

    operation_schedule = {
        s.operation_id: s
        for s in active_schedules
    }

    changeover_lookup = {
        (
            item.machine_id,
            item.from_product_id,
            item.to_product_id,
        ): item.changeover_minutes
        for item in changeovers
    }

    # Identify unique schedules with active downtime conflicts.
    conflicts = []

    for schedule in active_schedules:
        for downtime in active_downtimes:
            if schedule.machine_id != downtime.machine_id:
                continue

            if overlaps(
                schedule.start_time,
                schedule.end_time,
                downtime.start_time,
                downtime.end_time,
            ):
                conflicts.append(schedule)
                break

    print("\nREAD-ONLY REPAIR CANDIDATE VALIDATION")
    print("=" * 75)
    print("Total schedules:", len(schedules))
    print("Unique downtime-conflicted schedules:", len(conflicts))

    passed = 0
    failed = 0
    all_candidates = []

    for current in conflicts:

        operation = current.operation
        order = operation.production_order
        duration = current.end_time - current.start_time

        previous_ops = [
            op for op in operations
            if op.production_order_id == operation.production_order_id
            and op.sequence_number < operation.sequence_number
        ]

        next_ops = [
            op for op in operations
            if op.production_order_id == operation.production_order_id
            and op.sequence_number > operation.sequence_number
        ]

        earliest_start = current.start_time
        next_operation_start = None
        precedence_problem = None

        if previous_ops:
            previous_op = max(
                previous_ops,
                key=lambda op: op.sequence_number,
            )

            previous_schedule = operation_schedule.get(previous_op.id)

            if previous_schedule is None:
                precedence_problem = (
                    f"Previous operation {previous_op.operation_code} "
                    "has no active schedule"
                )
            else:
                earliest_start = max(
                    earliest_start,
                    previous_schedule.end_time,
                )

        if next_ops:
            next_op = min(
                next_ops,
                key=lambda op: op.sequence_number,
            )

            next_schedule = operation_schedule.get(next_op.id)

            if next_schedule:
                next_operation_start = next_schedule.start_time

        print("\n" + "-" * 75)
        print("Schedule:", current.schedule_code)
        print("Operation:", operation.operation_code)
        print("Current machine:", current.machine.machine_code)

        if precedence_problem:
            print("PRECEDENCE WARNING:", precedence_problem)
            failed += 1
            continue

        eligible_machines = operation.routing_step.eligible_machines
        candidates = []

        for machine in eligible_machines:

            if machine.status and machine.status.lower() != "active":
                continue

            machine_calendars = [
                c for c in calendars
                if c.machine_id == machine.id
                and c.status
                and c.status.lower() == "available"
                and c.shift_end > earliest_start
            ]

            machine_calendars.sort(
                key=lambda c: c.shift_start
            )

            for calendar in machine_calendars:

                candidate, reason = find_candidate_slot(
                    machine,
                    calendar,
                    earliest_start,
                    duration,
                    operation,
                    current,
                    active_schedules,
                    active_downtimes,
                    inventory_lots,
                    changeover_lookup,
                )

                if candidate is None:
                    continue

                if (
                    next_operation_start is not None
                    and candidate["end"] > next_operation_start
                ):
                    continue

                candidates.append(candidate)

                # Earliest valid slot for this machine.
                break

        candidates.sort(key=lambda c: c["start"])

        if candidates:
            passed += 1

            print("VALID CANDIDATE OPTIONS:")

            for candidate in candidates[:3]:
                print(
                    f"  {candidate['machine']} | "
                    f"{candidate['start']} to {candidate['end']} | "
                    f"Changeover: "
                    f"{candidate['changeover_minutes']} minutes"
                )

            # Keep earliest option for cross-candidate analysis.
            all_candidates.append({
                "schedule": current.schedule_code,
                **candidates[0],
            })

        else:
            failed += 1
            print("NO VALID CANDIDATE FOUND")

    # Check whether the earliest options of different schedules
    # overlap on the same proposed machine.
    print("\n" + "=" * 75)
    print("POTENTIAL CONFLICTS BETWEEN EARLIEST CANDIDATE OPTIONS")

    pair_conflicts = 0

    for i, first in enumerate(all_candidates):
        for second in all_candidates[i + 1:]:

            if first["machine_id"] != second["machine_id"]:
                continue

            if overlaps(
                first["start"],
                first["end"],
                second["start"],
                second["end"],
            ):
                pair_conflicts += 1

                print(
                    first["schedule"],
                    "and",
                    second["schedule"],
                    "both propose",
                    first["machine"],
                    "|",
                    first["start"],
                    "to",
                    first["end"],
                    "vs",
                    second["start"],
                    "to",
                    second["end"],
                )

    if pair_conflicts == 0:
        print("No overlaps among the earliest candidate options.")

    print("\n" + "=" * 75)
    print("FINAL SUMMARY")
    print("Schedules with valid individual options:", passed)
    print("Schedules without valid options:", failed)
    print("Potential candidate-to-candidate overlaps:", pair_conflicts)

    print("\nIMPORTANT:")
    print("- This script only reads the BACKUP database.")
    print("- No schedules, inventory, or events were modified.")
    print("- Each schedule is evaluated independently.")
    print("- Candidate-to-candidate overlaps need joint plan selection.")
    print("- Material validation requires one eligible lot per requirement.")
    print("- Machine capacity is not checked because its unit/meaning")
    print("  is not established by the current scheduler logic.")

finally:
    db.close()
