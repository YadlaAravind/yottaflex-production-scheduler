from datetime import timedelta
from pathlib import Path

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

# =========================================================
# READ-ONLY BACKUP DATABASE
# =========================================================

engine = create_engine(
    "sqlite:///file:yottaflex_generated_backup.db?mode=ro&uri=true",
    connect_args={"check_same_thread": False},
)

Session = sessionmaker(bind=engine)

MAX_SEARCH_NODES = 50000
MAX_CANDIDATES_PER_SCHEDULE = 20
EPSILON = 0.000001

OUTPUT_FILE = Path("global_reschedule_plan_v2_output.txt")


# =========================================================
# GENERAL HELPERS
# =========================================================

def is_active(record):
    status = getattr(record, "status", None)

    if status is None:
        return True

    return str(status).strip().lower() not in {
        "cancelled",
        "canceled",
        "inactive",
        "deleted",
    }


def machine_is_active(machine):
    status = getattr(machine, "status", None)

    return (
        status is None
        or str(status).strip().lower()
        in {"active", "available", "running"}
    )


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


def get_changeover(machine_id, from_product, to_product, lookup):
    if from_product == to_product:
        return 0

    key = (machine_id, from_product, to_product)

    # Missing changeover information is unknown.
    # Never assume that it means zero minutes.
    if key not in lookup:
        return None

    value = lookup[key]

    if value is None:
        return None

    return float(value)


# =========================================================
# MATERIAL VALIDATION
# =========================================================

def check_all_materials(
    active_schedules,
    assignments,
    requirements,
    inventory,
):
    """
    Validate material consumption across ALL active schedules.

    Proposed schedules use their proposed start times.
    Unplaced schedules retain their original start times.
    Fixed schedules are also included.

    Inventory is consumed using FIFO lot allocation.
    """

    usage = []

    for schedule in active_schedules:

        assignment = assignments.get(schedule.id)

        start = (
            assignment["start"]
            if assignment
            else schedule.start_time
        )

        for req in requirements.get(schedule.operation_id, []):

            usage.append({
                "material_id": req.material_id,
                "quantity": float(req.quantity_required or 0),
                "start": start,
                "schedule_code": schedule.schedule_code,
            })

    usage.sort(
        key=lambda item: (
            item["start"],
            item["schedule_code"],
        )
    )

    remaining = {
        lot.id: float(lot.quantity or 0)
        for lot in inventory
    }

    for item in usage:

        needed = item["quantity"]

        if needed <= EPSILON:
            continue

        suitable_lots = [
            lot
            for lot in inventory
            if (
                lot.material_id == item["material_id"]
                and str(lot.status or "").strip().lower()
                == "available"
                and lot.available_at is not None
                and lot.available_at <= item["start"]
                and (
                    lot.expiry_at is None
                    or lot.expiry_at >= item["start"]
                )
                and remaining[lot.id] > EPSILON
            )
        ]

        suitable_lots.sort(
            key=lambda lot: (
                lot.expiry_at is None,
                lot.expiry_at or lot.available_at,
                lot.available_at,
                lot.id,
            )
        )

        for lot in suitable_lots:

            used = min(
                needed,
                remaining[lot.id],
            )

            remaining[lot.id] -= used
            needed -= used

            if needed <= EPSILON:
                break

        if needed > EPSILON:
            return False, {
                "schedule_code": item["schedule_code"],
                "material_id": item["material_id"],
                "shortage": needed,
            }

    return True, None


# =========================================================
# PRECEDENCE HELPERS
# =========================================================

def get_predecessor_time(
    current,
    operations_by_order,
    schedule_by_operation,
    conflict_ids,
    assignments,
    skipped,
):
    """
    A schedule cannot start before its scheduled predecessors finish.

    If a predecessor is conflicted, it must already have a proposed
    assignment. If it was skipped, the current operation is also skipped.
    """

    operation = current.operation

    previous_ops = [
        op
        for op in operations_by_order.get(
            operation.production_order_id,
            [],
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

        if not is_active(previous_schedule):
            continue

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

        else:

            earliest = max(
                earliest,
                previous_schedule.end_time,
            )

    return earliest, None


def get_successor_limit(
    current,
    operations_by_order,
    schedule_by_operation,
    conflict_ids,
):
    operation = current.operation

    next_ops = [
        op
        for op in operations_by_order.get(
            operation.production_order_id,
            []
        )
        if op.sequence_number > operation.sequence_number
    ]

    starts = []

    for next_op in next_ops:
        next_schedule = schedule_by_operation.get(next_op.id)

        if next_schedule is None:
            continue

        if not is_active(next_schedule):
            continue

        if next_schedule.id in conflict_ids:
            continue

        starts.append(next_schedule.start_time)

    return min(starts) if starts else None

# =========================================================
# MACHINE BOOKINGS
# =========================================================

def generate_candidates(
    current,
    earliest_start,
    successor_limit,
    machines,
    calendars,
    active_schedules,
    assignments,
    downtimes,
    changeover_lookup,
    conflict_ids,
):
    operation = current.operation

    rejection_stats = {
        "no_routing_step": 0,
        "invalid_duration": 0,
        "no_eligible_machine": 0,
        "no_matching_calendar": 0,
        "capacity": 0,
        "cursor_after_shift": 0,
        "duration_exceeds_shift": 0,
        "unknown_changeover_before": 0,
        "successor_limit": 0,
        "blocking_booking": 0,
        "unknown_changeover_after": 0,
        "changeover_gap": 0,
    }

    candidates = []

    if operation.routing_step is None:
        rejection_stats["no_routing_step"] += 1
        print(
            f"REJECTION DETAILS | {current.schedule_code} | "
            f"{rejection_stats} | Candidates: 0"
        )
        return []

    duration = current.end_time - current.start_time

    if duration.total_seconds() <= 0:
        rejection_stats["invalid_duration"] += 1
        print(
            f"REJECTION DETAILS | {current.schedule_code} | "
            f"{rejection_stats} | Candidates: 0"
        )
        return []

    duration_minutes = duration.total_seconds() / 60
    product_id = operation.production_order.product_id

    eligible_machine_ids = {
        machine.id
        for machine in operation.routing_step.eligible_machines
        if machine_is_active(machine)
    }

    eligible_machines = [
        machine
        for machine in machines
        if machine.id in eligible_machine_ids
    ]

    if not eligible_machines:
        rejection_stats["no_eligible_machine"] += 1

    calendar_options = [
        calendar
        for calendar in calendars
        if (
            calendar.machine_id in eligible_machine_ids
            and str(calendar.status or "").strip().lower()
            == "available"
            and calendar.shift_end > earliest_start
            and calendar.available_minutes is not None
            and calendar.available_minutes >= duration_minutes
        )
    ]

    if not calendar_options:
        rejection_stats["no_matching_calendar"] += 1

    print(
        f"FILTER CHECK | {current.schedule_code} | "
        f"Eligible machines: {len(eligible_machines)} | "
        f"Matching calendars: {len(calendar_options)} | "
        f"Duration: {duration_minutes:.1f} min"
    )

    for machine in eligible_machines:

        machine_calendars = [
            calendar
            for calendar in calendars
            if (
                calendar.machine_id == machine.id
                and str(calendar.status or "").strip().lower()
                == "available"
                and calendar.shift_end > earliest_start
                and calendar.available_minutes is not None
                and calendar.available_minutes >= duration_minutes
            )
        ]

        machine_calendars.sort(
            key=lambda calendar: calendar.shift_start
        )

        bookings = get_machine_bookings(
            machine_id=machine.id,
            current_schedule_id=current.id,
            active_schedules=active_schedules,
            assignments=assignments,
            downtimes=downtimes,
            conflict_ids=conflict_ids,
        )

        schedule_bookings = [
            item
            for item in bookings
            if item["kind"] == "schedule"
        ]

        for calendar in machine_calendars:

            cursor = max(
                calendar.shift_start,
                earliest_start,
            )

            if cursor >= calendar.shift_end:
                rejection_stats["cursor_after_shift"] += 1
                continue

            booked_minutes = sum(
                max(
                    0,
                    (
                        min(
                            item["end"],
                            calendar.shift_end,
                        )
                        - max(
                            item["start"],
                            calendar.shift_start,
                        )
                    ).total_seconds() / 60,
                )
                for item in schedule_bookings
                if overlaps(
                    item["start"],
                    item["end"],
                    calendar.shift_start,
                    calendar.shift_end,
                )
            )

            if (
                booked_minutes + duration_minutes
                > calendar.available_minutes + EPSILON
            ):
                rejection_stats["capacity"] += 1
                continue

            iterations = 0

            while iterations < 500:

                iterations += 1

                if cursor + duration > calendar.shift_end:
                    rejection_stats["duration_exceeds_shift"] += 1
                    break

                previous_bookings = [
                    item
                    for item in schedule_bookings
                    if item["end"] <= cursor
                ]

                previous = (
                    max(
                        previous_bookings,
                        key=lambda item: item["end"],
                    )
                    if previous_bookings
                    else None
                )

                changeover_before = 0

                if previous:

                    changeover_before = get_changeover(
                        machine.id,
                        previous["product_id"],
                        product_id,
                        changeover_lookup,
                    )

                    if changeover_before is None:

                        rejection_stats[
                            "unknown_changeover_before"
                        ] += 1

                        future_events = [
                            item
                            for item in bookings
                            if item["end"] > cursor
                        ]

                        if not future_events:
                            break

                        next_event = min(
                            future_events,
                            key=lambda item: item["end"],
                        )

                        cursor = max(
                            cursor,
                            next_event["end"],
                        )

                        continue

                candidate_start = cursor

                if previous:
                    candidate_start = max(
                        candidate_start,
                        previous["end"]
                        + timedelta(minutes=changeover_before),
                    )

                candidate_end = candidate_start + duration

                if candidate_end > calendar.shift_end:
                    rejection_stats["duration_exceeds_shift"] += 1
                    break

                if (
                    successor_limit is not None
                    and candidate_end > successor_limit
                ):
                    rejection_stats["successor_limit"] += 1
                    break

                blocking_event = next(
                    (
                        item
                        for item in bookings
                        if overlaps(
                            candidate_start,
                            candidate_end,
                            item["start"],
                            item["end"],
                        )
                    ),
                    None,
                )

                if blocking_event:

                    rejection_stats["blocking_booking"] += 1

                    cursor = max(
                        cursor,
                        blocking_event["end"],
                    )

                    continue

                following_bookings = [
                    item
                    for item in schedule_bookings
                    if item["start"] >= candidate_end
                ]

                following = (
                    min(
                        following_bookings,
                        key=lambda item: item["start"],
                    )
                    if following_bookings
                    else None
                )

                changeover_after = 0

                if following:

                    changeover_after = get_changeover(
                        machine.id,
                        product_id,
                        following["product_id"],
                        changeover_lookup,
                    )

                    if changeover_after is None:

                        rejection_stats[
                            "unknown_changeover_after"
                        ] += 1

                        cursor = max(
                            cursor,
                            following["end"],
                        )

                        continue

                    required_end = (
                        candidate_end
                        + timedelta(minutes=changeover_after)
                    )

                    if required_end > following["start"]:

                        rejection_stats["changeover_gap"] += 1

                        cursor = max(
                            cursor,
                            following["end"],
                        )

                        continue

                candidates.append({
                    "schedule_id": current.id,
                    "schedule_code": current.schedule_code,
                    "operation_id": operation.id,
                    "machine_id": machine.id,
                    "machine_code": machine.machine_code,
                    "start": candidate_start,
                    "end": candidate_end,
                    "product_id": product_id,
                })

                if len(candidates) >= MAX_CANDIDATES_PER_SCHEDULE:
                    break

                cursor = candidate_end

            if len(candidates) >= MAX_CANDIDATES_PER_SCHEDULE:
                break

        if len(candidates) >= MAX_CANDIDATES_PER_SCHEDULE:
            break

    candidates.sort(
        key=lambda item: (
            item["start"],
            item["machine_code"],
        )
    )

    print(
        f"REJECTION DETAILS | {current.schedule_code} | "
        f"{rejection_stats} | Candidates: {len(candidates)}"
    )

    return candidates

# =========================================================
# FINAL VALIDATION
# =========================================================

def validate_final_plan(
    active_schedules,
    assignments,
    downtimes,
    operations_by_order,
    requirements,
    inventory,
):
    overlap_errors = []
    downtime_errors = []
    precedence_errors = []

    # -----------------------------------------------------
    # Build final bookings for every active schedule.
    # -----------------------------------------------------

    final_bookings = []

    for schedule in active_schedules:

        assignment = assignments.get(schedule.id)

        if assignment:

            final_bookings.append({
                "code": schedule.schedule_code,
                "operation_id": schedule.operation_id,
                "machine_id": assignment["machine_id"],
                "start": assignment["start"],
                "end": assignment["end"],
            })

        else:

            final_bookings.append({
                "code": schedule.schedule_code,
                "operation_id": schedule.operation_id,
                "machine_id": schedule.machine_id,
                "start": schedule.start_time,
                "end": schedule.end_time,
            })

    # -----------------------------------------------------
    # Machine overlap validation.
    # Check every potentially overlapping pair.
    # -----------------------------------------------------

    by_machine = {}

    for booking in final_bookings:

        if booking["machine_id"] is None:
            overlap_errors.append(
                (booking["code"], "MISSING_MACHINE")
            )
            continue

        by_machine.setdefault(
            booking["machine_id"],
            [],
        ).append(booking)

    for machine_id, items in by_machine.items():

        items.sort(
            key=lambda item: (
                item["start"],
                item["end"],
            )
        )

        for index, first in enumerate(items):

            for second in items[index + 1:]:

                if second["start"] >= first["end"]:
                    break

                if overlaps(
                    first["start"],
                    first["end"],
                    second["start"],
                    second["end"],
                ):
                    overlap_errors.append(
                        (
                            first["code"],
                            second["code"],
                        )
                    )

    # -----------------------------------------------------
    # Downtime validation.
    # -----------------------------------------------------

    for booking in final_bookings:

        for downtime in downtimes:

            if downtime.machine_id != booking["machine_id"]:
                continue

            if overlaps(
                booking["start"],
                booking["end"],
                downtime.start_time,
                downtime.end_time,
            ):
                downtime_errors.append(
                    booking["code"]
                )

    # Remove duplicate downtime schedule codes.
    downtime_errors = sorted(set(downtime_errors))

    # -----------------------------------------------------
    # Precedence validation.
    # -----------------------------------------------------

    final_by_operation = {
        item["operation_id"]: item
        for item in final_bookings
    }

    for order_operations in operations_by_order.values():

        ordered_operations = sorted(
            order_operations,
            key=lambda item: item.sequence_number,
        )

        previous_end = None
        previous_code = None

        for operation in ordered_operations:

            current = final_by_operation.get(operation.id)

            if current is None:
                continue

            if (
                previous_end is not None
                and current["start"] < previous_end
            ):
                precedence_errors.append(
                    (
                        previous_code,
                        current["code"],
                    )
                )

            previous_end = current["end"]
            previous_code = current["code"]

    # -----------------------------------------------------
    # Material validation across all active schedules.
    # -----------------------------------------------------

    material_pass, material_issue = check_all_materials(
        active_schedules,
        assignments,
        requirements,
        inventory,
    )

    return {
        "overlaps": overlap_errors,
        "downtime": downtime_errors,
        "precedence": precedence_errors,
        "materials_pass": material_pass,
        "material_issue": material_issue,
    }


# =========================================================
# PLAN SAFETY CHECK
# =========================================================

def is_safe_partial_plan(validation, assignments):
    """
    A partial plan may retain downtime conflicts ONLY for
    schedules that were not assigned a proposed repair.

    All other safety checks apply to the entire active schedule set.
    """

    assigned_codes = {
        item["schedule_code"]
        for item in assignments.values()
    }

    assigned_downtime_conflicts = [
        code
        for code in validation["downtime"]
        if code in assigned_codes
    ]

    return (
        not validation["overlaps"]
        and not assigned_downtime_conflicts
        and not validation["precedence"]
        and validation["materials_pass"]
    )


# =========================================================
# MAIN PLANNER
# =========================================================

def main():

    db = Session()

    try:

        print("Loading backup database in READ-ONLY mode...")

        schedules = db.query(OperationSchedule).all()
        operations = db.query(Operation).all()
        machines = db.query(Machine).all()
        calendars = db.query(MachineCalendar).all()
        downtimes = db.query(MachineDowntime).all()
        inventory = db.query(InventoryLot).all()

        requirements_list = (
            db.query(OperationMaterialRequirement).all()
        )

        changeovers = db.query(ChangeoverMatrix).all()

        # -------------------------------------------------
        # Active records
        # -------------------------------------------------

        active_schedules = [
            item
            for item in schedules
            if is_active(item)
        ]

        active_downtimes = [
            item
            for item in downtimes
            if is_active(item)
        ]

        # -------------------------------------------------
        # Material requirements
        # -------------------------------------------------

        requirements = {}

        for req in requirements_list:

            requirements.setdefault(
                req.operation_id,
                [],
            ).append(req)

        # -------------------------------------------------
        # Changeover lookup
        # -------------------------------------------------

        changeover_lookup = {
            (
                item.machine_id,
                item.from_product_id,
                item.to_product_id,
            ): item.changeover_minutes
            for item in changeovers
        }

        # -------------------------------------------------
        # Find downtime-conflicted schedules.
        # -------------------------------------------------

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
            item.id
            for item in conflicts
        }

        # -------------------------------------------------
        # One active schedule per operation is expected.
        # -------------------------------------------------

        schedule_by_operation = {}

        for schedule in active_schedules:

            if schedule.operation_id in schedule_by_operation:

                raise ValueError(
                    "Multiple active schedules found for operation "
                    f"{schedule.operation_id}. "
                    "Resolve this ambiguity before running the planner."
                )

            schedule_by_operation[schedule.operation_id] = schedule

        # -------------------------------------------------
        # Group operations by production order.
        # -------------------------------------------------

        operations_by_order = {}

        for operation in operations:

            operations_by_order.setdefault(
                operation.production_order_id,
                [],
            ).append(operation)

        for order_operations in operations_by_order.values():

            order_operations.sort(
                key=lambda item: item.sequence_number
            )

        # -------------------------------------------------
        # Sort conflicts in production sequence order.
        # -------------------------------------------------

        conflicts.sort(
            key=lambda item: (
                item.operation.production_order_id,
                item.operation.sequence_number,
                item.start_time,
            )
        )

        # -------------------------------------------------
        # Search state
        # -------------------------------------------------

        assignments = {}
        skipped = set()

        best_assignments = {}
        best_validation = None

        search_nodes = 0
        search_limit_reached = False
        full_solution_found = False

        # =================================================
        # BACKTRACKING SEARCH
        # =================================================

        def search(index):

            nonlocal search_nodes
            nonlocal search_limit_reached
            nonlocal full_solution_found
            nonlocal best_assignments
            nonlocal best_validation

            if search_limit_reached or full_solution_found:
                return

            search_nodes += 1

            if search_nodes > MAX_SEARCH_NODES:

                search_limit_reached = True
                return

            remaining = len(conflicts) - index

            # Prune branches that cannot improve the best plan.
            if (
                len(assignments) + remaining
                <= len(best_assignments)
            ):
                return

            # -------------------------------------------------
            # All conflicted schedules have been considered.
            # -------------------------------------------------

            if index == len(conflicts):

                validation = validate_final_plan(
                    active_schedules=active_schedules,
                    assignments=assignments,
                    downtimes=active_downtimes,
                    operations_by_order=operations_by_order,
                    requirements=requirements,
                    inventory=inventory,
                )

                # IMPORTANT FIX:
                # Accept a safe PARTIAL plan.
                # Downtime conflicts are allowed only for
                # schedules that remain unplaced.
                if is_safe_partial_plan(
                    validation,
                    assignments,
                ):

                    if len(assignments) > len(best_assignments):

                        best_assignments = dict(assignments)
                        best_validation = validation

                    if len(best_assignments) == len(conflicts):

                        full_solution_found = True

                return

            current = conflicts[index]

            # -------------------------------------------------
            # Determine earliest possible start.
            # -------------------------------------------------

            earliest, error = get_predecessor_time(
                current=current,
                operations_by_order=operations_by_order,
                schedule_by_operation=schedule_by_operation,
                conflict_ids=conflict_ids,
                assignments=assignments,
                skipped=skipped,
            )

            if error:

                # This schedule cannot safely be repaired
                # under the current predecessor plan.
                skipped.add(current.id)

                search(index + 1)

                skipped.remove(current.id)

                return

            # -------------------------------------------------
            # Determine successor time limit.
            # -------------------------------------------------

            successor_limit = get_successor_limit(
    current=current,
    operations_by_order=operations_by_order,
    schedule_by_operation=schedule_by_operation,
    conflict_ids=conflict_ids,
)

            # -------------------------------------------------
            # Generate candidate slots.
            # -------------------------------------------------

            candidates = generate_candidates(
                current=current,
                earliest_start=earliest,
                successor_limit=successor_limit,
                machines=machines,
                calendars=calendars,
                active_schedules=active_schedules,
                assignments=assignments,
                downtimes=active_downtimes,
                changeover_lookup=changeover_lookup,
            )
            print(
                f"DIAGNOSTIC | {current.schedule_code} | "
                f"Candidates found: {len(candidates)} | "
                f"Earliest: {earliest} | "
                f"Successor limit: {successor_limit}"
            )
            # -------------------------------------------------
            # Try each candidate.
            # -------------------------------------------------

            for candidate in candidates:

                assignments[current.id] = candidate

                search(index + 1)

                assignments.pop(current.id, None)

                if search_limit_reached or full_solution_found:
                    return

            # -------------------------------------------------
            # Also explore leaving this schedule unplaced.
            # Its original slot remains reserved.
            # -------------------------------------------------

            skipped.add(current.id)

            search(index + 1)

            skipped.remove(current.id)

        # =================================================
        # RUN SEARCH
        # =================================================

        print("Starting V2 global repair search...")
        print("Total active schedules:", len(active_schedules))
        print("Downtime-conflicted schedules:", len(conflicts))
        print("Search node limit:", MAX_SEARCH_NODES)

        search(0)

        # =================================================
        # FINAL PLAN
        # =================================================

        final_assignments = best_assignments

        final_validation = validate_final_plan(
            active_schedules=active_schedules,
            assignments=final_assignments,
            downtimes=active_downtimes,
            operations_by_order=operations_by_order,
            requirements=requirements,
            inventory=inventory,
        )

        unplaced = [
            item
            for item in conflicts
            if item.id not in final_assignments
        ]

        # Downtime conflicts belonging to unplaced schedules
        # are expected in a partial repair plan.
        assigned_codes = {
            item["schedule_code"]
            for item in final_assignments.values()
        }

        remaining_downtime_conflicts = [
            code
            for code in final_validation["downtime"]
            if code not in assigned_codes
        ]

        assigned_downtime_conflicts = [
            code
            for code in final_validation["downtime"]
            if code in assigned_codes
        ]

        # =================================================
        # REPORT
        # =================================================

        lines = []

        def report(value=""):
            lines.append(str(value))

        report("GLOBAL RESCHEDULE PLAN V2 - READ ONLY")
        report("=" * 80)

        report(f"Total existing schedules: {len(schedules)}")
        report(f"Active schedules: {len(active_schedules)}")
        report(f"Downtime-conflicted schedules: {len(conflicts)}")
        report(f"Proposed repairs: {len(final_assignments)}")
        report(f"Unplaced schedules: {len(unplaced)}")
        report(f"Search nodes: {search_nodes}")
        report(f"Search limit reached: {search_limit_reached}")
        report(f"Complete solution found: {full_solution_found}")

        report()

        # -------------------------------------------------
        # Proposed repairs
        # -------------------------------------------------

        report("PROPOSED REPAIR PLAN")
        report("-" * 80)

        for item in sorted(
            final_assignments.values(),
            key=lambda x: (
                x["start"],
                x["machine_code"],
            ),
        ):

            report(
                f'{item["schedule_code"]} | '
                f'{item["machine_code"]} | '
                f'{item["start"]} to {item["end"]}'
            )

        report()

        # -------------------------------------------------
        # Unplaced schedules
        # -------------------------------------------------

        report("UNPLACED SCHEDULES")
        report("-" * 80)

        for item in unplaced:

            report(
                f"{item.schedule_code} | "
                f"Original machine: {item.machine.machine_code} | "
                f"Original time: "
                f"{item.start_time} to {item.end_time}"
            )

        report()

        # -------------------------------------------------
        # Final validation
        # -------------------------------------------------

        report("FINAL VALIDATION - ALL ACTIVE SCHEDULES")
        report("-" * 80)

        report(
            f"Machine overlap errors: "
            f"{len(final_validation['overlaps'])}"
        )

        report(
            f"Downtime conflicts remaining: "
            f"{len(remaining_downtime_conflicts)}"
        )

        report(
            f"Downtime conflicts in proposed repairs: "
            f"{len(assigned_downtime_conflicts)}"
        )

        report(
            f"Precedence errors: "
            f"{len(final_validation['precedence'])}"
        )

        report(
            f"All-schedule material check: "
            f"{final_validation['materials_pass']}"
        )

        report(
            f"Safe partial plan: "
            f"{is_safe_partial_plan(final_validation, final_assignments)}"
        )

        if final_validation["material_issue"]:

            report(
                f"Material issue: "
                f"{final_validation['material_issue']}"
            )

        report()

        # -------------------------------------------------
        # Detailed errors
        # -------------------------------------------------

        report("MACHINE OVERLAP DETAILS")
        report("-" * 80)

        for first, second in final_validation["overlaps"]:
            report(f"OVERLAP: {first} / {second}")

        report()

        report("REMAINING DOWNTIME CONFLICTS")
        report("-" * 80)

        for code in remaining_downtime_conflicts:
            report(f"UNPLACED DOWNTIME CONFLICT: {code}")

        report()

        report("PROPOSED REPAIR DOWNTIME ERRORS")
        report("-" * 80)

        for code in assigned_downtime_conflicts:
            report(f"PROPOSED REPAIR ERROR: {code}")

        report()

        report("PRECEDENCE ERRORS")
        report("-" * 80)

        for previous, following in final_validation["precedence"]:
            report(f"PRECEDENCE: {previous} -> {following}")

        report()

        # -------------------------------------------------
        # Limitations
        # -------------------------------------------------

        report("IMPORTANT LIMITATIONS")
        report("-" * 80)

        report(
            "- Search is bounded and is not guaranteed to find "
            "the globally optimal plan."
        )

        report(
            "- Candidate generation is limited to "
            f"{MAX_CANDIDATES_PER_SCHEDULE} candidates per schedule."
        )

        report(
            "- Unplaced schedules retain their original "
            "machine and time bookings."
        )

        report(
            "- Missing changeover entries are treated as unknown."
        )

        report(
            "- Same-product transitions are treated as zero changeover."
        )

        report(
            "- Material validation uses aggregate FIFO lot allocation."
        )

        report(
            "- External material reservations are not available "
            "to this database check."
        )

        report(
            "- Calendar available_minutes is checked against "
            "existing booked schedule time."
        )

        report(
            "- The planner does not modify the database."
        )

        # -------------------------------------------------
        # Save report
        # -------------------------------------------------

        OUTPUT_FILE.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        # =================================================
        # CONSOLE SUMMARY
        # =================================================

        print("\n" + "=" * 65)
        print("V2 PLANNER SUMMARY")
        print("=" * 65)

        print("Conflicted schedules:", len(conflicts))
        print("Proposed repairs:", len(final_assignments))
        print("Unplaced:", len(unplaced))
        print("Search nodes:", search_nodes)
        print("Search limit reached:", search_limit_reached)
        print("Complete solution found:", full_solution_found)

        print(
            "Machine overlaps:",
            len(final_validation["overlaps"]),
        )

        print(
            "Remaining downtime conflicts:",
            len(remaining_downtime_conflicts),
        )

        print(
            "Proposed repair downtime errors:",
            len(assigned_downtime_conflicts),
        )

        print(
            "Precedence errors:",
            len(final_validation["precedence"]),
        )

        print(
            "All-schedule material check:",
            final_validation["materials_pass"],
        )

        print(
            "Safe partial plan:",
            is_safe_partial_plan(
                final_validation,
                final_assignments,
            ),
        )

        print("\nReport saved:", OUTPUT_FILE)

        print("\nDatabase modified: NO")

    finally:
        db.close()


if __name__ == "__main__":
    main()
