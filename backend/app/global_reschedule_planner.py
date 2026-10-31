
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Operation,
    OperationSchedule,
    MachineDowntime,
    MachineCalendar,
    InventoryLot,
    OperationMaterialRequirement,
    ChangeoverMatrix,
)

# --------------------------------------------------
# STRICT READ-ONLY BACKUP DATABASE
# --------------------------------------------------

engine = create_engine(
    "sqlite:///file:yottaflex_generated_backup.db?mode=ro&uri=true",
    connect_args={"check_same_thread": False},
)

Session = sessionmaker(bind=engine)
db = Session()

MAX_SEARCH_NODES = 50000
MAX_CANDIDATES_PER_SCHEDULE = 8

OUTPUT_FILE = Path("global_reschedule_plan_output.txt")


def is_active(record):
    status = getattr(record, "status", None)
    return status is None or status.lower() not in (
        "cancelled",
        "canceled",
    )


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


def get_changeover(machine_id, from_product, to_product, lookup):
    key = (machine_id, from_product, to_product)

    if key not in lookup:
        return 0, True

    return lookup[key], False


def check_materials(assignments, requirements, inventory):
    """
    Aggregate material check across all proposed repairs.
    Existing non-conflicted schedule consumption is NOT deducted.
    """

    usage = []

    for schedule_id, candidate in assignments.items():
        for req in requirements.get(candidate["operation_id"], []):
            usage.append({
                "material_id": req.material_id,
                "quantity": req.quantity_required,
                "start": candidate["start"],
                "schedule": candidate["schedule_code"],
            })

    usage.sort(key=lambda x: x["start"])

    remaining = {
        lot.id: lot.quantity
        for lot in inventory
    }

    for item in usage:
        needed = item["quantity"]

        suitable_lots = [
            lot for lot in inventory
            if lot.material_id == item["material_id"]
            and lot.status
            and lot.status.lower() == "available"
            and lot.available_at <= item["start"]
            and (
                lot.expiry_at is None
                or lot.expiry_at > item["start"]
            )
            and remaining[lot.id] > 0
        ]

        suitable_lots.sort(
            key=lambda lot: (
                lot.expiry_at is None,
                lot.expiry_at or lot.available_at,
                lot.available_at,
            )
        )

        for lot in suitable_lots:
            used = min(needed, remaining[lot.id])
            remaining[lot.id] -= used
            needed -= used

            if needed <= 0.000001:
                break

        if needed > 0.000001:
            return False

    return True


def get_predecessor_time(
    current,
    operations_by_order,
    schedule_by_operation,
    conflict_ids,
    assignments,
    skipped,
):
    operation = current.operation
    previous_ops = [
        op for op in operations_by_order.get(
            operation.production_order_id, []
        )
        if op.sequence_number < operation.sequence_number
    ]

    earliest = current.start_time

    for previous_op in previous_ops:
        previous_schedule = schedule_by_operation.get(
            previous_op.id
        )

        if previous_schedule is None:
            return None, "PREDECESSOR_SCHEDULE_MISSING"

        if previous_schedule.id in conflict_ids:
            if previous_schedule.id in skipped:
                return None, "PREDECESSOR_NOT_REPAIRED"

            previous_assignment = assignments.get(
                previous_schedule.id
            )

            if previous_assignment is None:
                return None, "PREDECESSOR_NOT_PLANNED"

            earliest = max(
                earliest,
                previous_assignment["end"],
            )

        elif is_active(previous_schedule):
            earliest = max(
                earliest,
                previous_schedule.end_time,
            )

    return earliest, None


def get_fixed_successor_start(
    current,
    operations_by_order,
    schedule_by_operation,
    conflict_ids,
):
    operation = current.operation

    next_ops = [
        op for op in operations_by_order.get(
            operation.production_order_id, []
        )
        if op.sequence_number > operation.sequence_number
    ]

    fixed_starts = []

    for next_op in next_ops:
        next_schedule = schedule_by_operation.get(next_op.id)

        if next_schedule is None:
            continue

        if (
            next_schedule.id not in conflict_ids
            and is_active(next_schedule)
        ):
            fixed_starts.append(next_schedule.start_time)

    return min(fixed_starts) if fixed_starts else None


def generate_candidates(
    current,
    earliest_start,
    next_start,
    machines,
    calendars,
    fixed_schedules,
    downtimes,
    reservations,
    changeover_lookup,
):
    operation = current.operation
    duration = current.end_time - current.start_time

    product_id = operation.production_order.product_id

    candidates = []

    eligible_machine_ids = {
        machine.id
        for machine in operation.routing_step.eligible_machines
        if not machine.status
        or machine.status.lower() == "active"
    }

    for machine in machines:
        if machine.id not in eligible_machine_ids:
            continue

        machine_calendars = [
            calendar for calendar in calendars
            if calendar.machine_id == machine.id
            and calendar.status
            and calendar.status.lower() == "available"
            and calendar.shift_end > earliest_start
            and calendar.available_minutes >= (
                duration.total_seconds() / 60
            )
        ]

        machine_calendars.sort(
            key=lambda calendar: calendar.shift_start
        )

        for calendar in machine_calendars:

            cursor = max(
                calendar.shift_start,
                earliest_start,
            )

            if cursor >= calendar.shift_end:
                continue

            busy = []

            # Fixed non-conflicted schedules.
            for schedule in fixed_schedules:
                if schedule.machine_id != machine.id:
                    continue

                busy.append({
                    "start": schedule.start_time,
                    "end": schedule.end_time,
                    "product_id": (
                        schedule.operation.production_order.product_id
                    ),
                    "kind": "schedule",
                })

            # Previously selected proposed repairs.
            for item in reservations:
                if item["machine_id"] != machine.id:
                    continue

                busy.append({
                    "start": item["start"],
                    "end": item["end"],
                    "product_id": item["product_id"],
                    "kind": "schedule",
                })

            # Active downtime.
            for downtime in downtimes:
                if downtime.machine_id != machine.id:
                    continue

                busy.append({
                    "start": downtime.start_time,
                    "end": downtime.end_time,
                    "product_id": None,
                    "kind": "downtime",
                })

            busy.sort(key=lambda item: item["start"])

            # Search available gaps in this calendar.
            for _ in range(300):

                if cursor + duration > calendar.shift_end:
                    break

                previous_bookings = [
                    item for item in busy
                    if item["kind"] == "schedule"
                    and item["end"] <= cursor
                ]

                previous_booking = (
                    max(
                        previous_bookings,
                        key=lambda item: item["end"],
                    )
                    if previous_bookings else None
                )

                changeover_before = 0
                missing_before = False

                if previous_booking:
                    changeover_before, missing_before = (
                        get_changeover(
                            machine.id,
                            previous_booking["product_id"],
                            product_id,
                            changeover_lookup,
                        )
                    )

                    candidate_start = max(
                        cursor,
                        previous_booking["end"]
                        + timedelta(minutes=changeover_before),
                    )
                else:
                    candidate_start = cursor

                candidate_end = candidate_start + duration

                if candidate_end > calendar.shift_end:
                    break

                # Check fixed schedules, downtime and reservations.
                conflict = next(
                    (
                        item for item in busy
                        if overlaps(
                            candidate_start,
                            candidate_end,
                            item["start"],
                            item["end"],
                        )
                    ),
                    None,
                )

                if conflict:
                    cursor = max(cursor, conflict["end"])
                    continue

                # Ensure enough changeover time before next booking.
                next_bookings = [
                    item for item in busy
                    if item["kind"] == "schedule"
                    and item["start"] >= candidate_end
                ]

                next_booking = (
                    min(
                        next_bookings,
                        key=lambda item: item["start"],
                    )
                    if next_bookings else None
                )

                changeover_after = 0
                missing_after = False

                if next_booking:
                    changeover_after, missing_after = (
                        get_changeover(
                            machine.id,
                            product_id,
                            next_booking["product_id"],
                            changeover_lookup,
                        )
                    )

                    required_end = candidate_end + timedelta(
                        minutes=changeover_after
                    )

                    if required_end > next_booking["start"]:
                        cursor = next_booking["end"]
                        continue

                # Preserve precedence against fixed successors.
                if next_start and candidate_end > next_start:
                    break

                candidates.append({
                    "schedule_id": current.id,
                    "schedule_code": current.schedule_code,
                    "operation_id": operation.id,
                    "machine_id": machine.id,
                    "machine_code": machine.machine_code,
                    "start": candidate_start,
                    "end": candidate_end,
                    "product_id": product_id,
                    "changeover_before": changeover_before,
                    "missing_changeover": (
                        missing_before or missing_after
                    ),
                })

                # Move forward to discover another possible gap.
                cursor = candidate_end

    candidates.sort(
        key=lambda item: (
            item["start"],
            item["machine_code"],
        )
    )

    return candidates[:MAX_CANDIDATES_PER_SCHEDULE]


def main():
    schedules = db.query(OperationSchedule).all()
    operations = db.query(Operation).all()
    machines = db.query(__import__(
        "app.models", fromlist=["Machine"]
    ).Machine).all()

    calendars = db.query(MachineCalendar).all()
    downtimes = db.query(MachineDowntime).all()
    inventory = db.query(InventoryLot).all()

    requirements_list = (
        db.query(OperationMaterialRequirement).all()
    )

    changeovers = db.query(ChangeoverMatrix).all()

    active_schedules = [
        item for item in schedules if is_active(item)
    ]

    active_downtimes = [
        item for item in downtimes if is_active(item)
    ]

    changeover_lookup = {
        (
            item.machine_id,
            item.from_product_id,
            item.to_product_id,
        ): item.changeover_minutes
        for item in changeovers
    }

    requirements = {}

    for req in requirements_list:
        requirements.setdefault(
            req.operation_id, []
        ).append(req)

    # Identify all downtime-conflicted schedules.
    conflicts = []

    for schedule in active_schedules:
        if any(
            schedule.machine_id == downtime.machine_id
            and overlaps(
                schedule.start_time,
                schedule.end_time,
                downtime.start_time,
                downtime.end_time,
            )
            for downtime in active_downtimes
        ):
            conflicts.append(schedule)

    conflict_ids = {
        item.id for item in conflicts
    }

    # These schedules remain fixed.
    fixed_schedules = [
        item for item in active_schedules
        if item.id not in conflict_ids
    ]

    # One active schedule per operation is assumed.
    schedule_by_operation = {
        item.operation_id: item
        for item in active_schedules
    }

    operations_by_order = {}

    for operation in operations:
        operations_by_order.setdefault(
            operation.production_order_id, []
        ).append(operation)

    for order_operations in operations_by_order.values():
        order_operations.sort(
            key=lambda item: item.sequence_number
        )

    # Process operations in production-order sequence.
    conflicts.sort(
        key=lambda item: (
            item.operation.production_order_id,
            item.operation.sequence_number,
            item.start_time,
        )
    )

    assignments = {}
    reservations = []
    skipped = set()

    best_assignments = {}
    best_skipped = set()

    search_nodes = 0
    stopped = False

    def search(index):
        nonlocal search_nodes
        nonlocal stopped
        nonlocal best_assignments
        nonlocal best_skipped

        if stopped:
            return

        search_nodes += 1

        if search_nodes > MAX_SEARCH_NODES:
            stopped = True
            return

        remaining = len(conflicts) - index

        if (
            len(assignments) + remaining
            <= len(best_assignments)
        ):
            return

        if index == len(conflicts):

            if check_materials(
                assignments,
                requirements,
                inventory,
            ):
                if len(assignments) > len(best_assignments):
                    best_assignments = dict(assignments)
                    best_skipped = set(skipped)

                if len(best_assignments) == len(conflicts):
                    stopped = True

            return

        current = conflicts[index]

        earliest, error = get_predecessor_time(
            current,
            operations_by_order,
            schedule_by_operation,
            conflict_ids,
            assignments,
            skipped,
        )

        if error:
            skipped.add(current.id)
            search(index + 1)
            skipped.remove(current.id)
            return

        next_start = get_fixed_successor_start(
            current,
            operations_by_order,
            schedule_by_operation,
            conflict_ids,
        )

        candidates = generate_candidates(
            current=current,
            earliest_start=earliest,
            next_start=next_start,
            machines=machines,
            calendars=calendars,
            fixed_schedules=fixed_schedules,
            downtimes=active_downtimes,
            reservations=reservations,
            changeover_lookup=changeover_lookup,
        )

        # Try each possible placement.
        for candidate in candidates:

            assignments[current.id] = candidate
            reservations.append(candidate)

            search(index + 1)

            reservations.pop()
            assignments.pop(current.id)

            if stopped:
                return

        # Also consider leaving this schedule unrepaired.
        skipped.add(current.id)
        search(index + 1)
        skipped.remove(current.id)

    print("Starting global repair search...")

    search(0)

    # --------------------------------------------------
    # FINAL INDEPENDENT VALIDATION
    # --------------------------------------------------

    final_plan = list(best_assignments.values())

    overlap_errors = []

    for index, first in enumerate(final_plan):
        for second in final_plan[index + 1:]:

            if first["machine_id"] != second["machine_id"]:
                continue

            if overlaps(
                first["start"],
                first["end"],
                second["start"],
                second["end"],
            ):
                overlap_errors.append(
                    (
                        first["schedule_code"],
                        second["schedule_code"],
                    )
                )

    downtime_errors = []

    for item in final_plan:
        for downtime in active_downtimes:
            if (
                downtime.machine_id == item["machine_id"]
                and overlaps(
                    item["start"],
                    item["end"],
                    downtime.start_time,
                    downtime.end_time,
                )
            ):
                downtime_errors.append(item["schedule_code"])

    material_pass = check_materials(
        best_assignments,
        requirements,
        inventory,
    )

    unplaced = [
        item.schedule_code
        for item in conflicts
        if item.id not in best_assignments
    ]

    # --------------------------------------------------
    # REPORT
    # --------------------------------------------------

    lines = []

    def report(value=""):
        lines.append(str(value))

    report("GLOBAL RESCHEDULE PLAN - READ ONLY")
    report("=" * 80)
    report(f"Total existing schedules: {len(schedules)}")
    report(f"Downtime-conflicted schedules: {len(conflicts)}")
    report(f"Proposed repairs: {len(final_plan)}")
    report(f"Unplaced schedules: {len(unplaced)}")
    report(f"Search nodes: {search_nodes}")
    report(f"Search limit reached: {stopped}")
    report()

    report("PROPOSED REPAIR PLAN")
    report("-" * 80)

    for item in sorted(
        final_plan,
        key=lambda x: (x["start"], x["machine_code"]),
    ):
        report(
            f'{item["schedule_code"]} | '
            f'{item["machine_code"]} | '
            f'{item["start"]} to {item["end"]}'
        )

    report()
    report("UNPLACED SCHEDULES")
    report("-" * 80)

    for code in unplaced:
        report(code)

    report()
    report("FINAL CHECKS")
    report("-" * 80)
    report(f"Proposed slot overlaps: {len(overlap_errors)}")
    report(f"Downtime conflicts in proposals: {len(downtime_errors)}")
    report(f"Aggregate proposed material check: {material_pass}")

    if overlap_errors:
        report("OVERLAP DETAILS:")
        for first, second in overlap_errors:
            report(f"{first} overlaps {second}")

    if downtime_errors:
        report("DOWNTIME DETAILS:")
        for code in downtime_errors:
            report(code)

    report()
    report("IMPORTANT LIMITATIONS")
    report("-" * 80)
    report("- This is a bounded backtracking search, not a proven global optimum.")
    report("- Existing non-conflicted schedules are treated as fixed.")
    report("- Existing jobs' material consumption is not deducted.")
    report("- Missing changeover matrix entries are treated as zero.")
    report("- Material quantities are aggregated across proposed repairs only.")
    report("- Changeover time across downtime and calendar boundaries needs review.")
    report("- No database records were inserted, updated, or deleted.")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\nGLOBAL PLAN SUMMARY")
    print("=" * 60)
    print("Conflicted schedules:", len(conflicts))
    print("Proposed repairs:", len(final_plan))
    print("Unplaced:", len(unplaced))
    print("Search nodes:", search_nodes)
    print("Search limit reached:", stopped)
    print("Proposal overlaps:", len(overlap_errors))
    print("Downtime errors:", len(downtime_errors))
    print("Material check:", material_pass)
    print("\nReport saved:", OUTPUT_FILE)


try:
    main()

finally:
    db.close()
