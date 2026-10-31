
import csv
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Machine,
    Product,
    ProductionOrder,
    Operation,
    OperationMaterialRequirement,
    InventoryLot,
    MachineCalendar,
    ChangeoverMatrix
)

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
db = Session()

output_dir = Path("../data")
output_dir.mkdir(exist_ok=True)

ground_truth = []

try:
    print("CREATING GROUND TRUTH DATA...\n")

    # GT-001: Machine overlap
    operations = (
        db.query(Operation)
        .order_by(Operation.id)
        .limit(2)
        .all()
    )

    machines = db.query(Machine).order_by(Machine.id).all()

    ground_truth.append({
        "case_id": "GT-001",
        "scenario": "machine_overlap",
        "entity_id": machines[0].machine_code,
        "related_entity_id": operations[0].operation_code,
        "description": "Two operations are assigned to the same machine during overlapping time periods.",
        "expected_violation": "Machine capacity conflict"
    })

    # GT-002: Operation precedence violation
    order = (
        db.query(ProductionOrder)
        .order_by(ProductionOrder.id)
        .first()
    )

    order_operations = (
        db.query(Operation)
        .filter_by(production_order_id=order.id)
        .order_by(Operation.sequence_number)
        .all()
    )

    ground_truth.append({
        "case_id": "GT-002",
        "scenario": "precedence_violation",
        "entity_id": order.order_code,
        "related_entity_id": order_operations[1].operation_code,
        "description": "A later operation is scheduled before its preceding operation.",
        "expected_violation": "Operation sequence constraint violated"
    })

    # GT-003: Material before availability
    requirement = (
        db.query(OperationMaterialRequirement)
        .order_by(OperationMaterialRequirement.id)
        .first()
    )

    inventory = (
        db.query(InventoryLot)
        .filter_by(material_id=requirement.material_id)
        .first()
    )

    ground_truth.append({
        "case_id": "GT-003",
        "scenario": "material_before_availability",
        "entity_id": requirement.operation.operation_code,
        "related_entity_id": inventory.lot_code,
        "description": "An operation attempts to consume material before its inventory lot becomes available.",
        "expected_violation": "Material availability constraint violated"
    })

    # GT-004: Outside machine shift
    calendar = (
        db.query(MachineCalendar)
        .order_by(MachineCalendar.id)
        .first()
    )

    calendar_machine = (
        db.query(Machine)
        .filter_by(id=calendar.machine_id)
        .first()
    )

    ground_truth.append({
        "case_id": "GT-004",
        "scenario": "outside_shift",
        "entity_id": calendar_machine.machine_code,
        "related_entity_id": str(calendar.shift_end),
        "description": "An operation is scheduled outside the machine's available shift.",
        "expected_violation": "Machine calendar constraint violated"
    })

    # GT-005: Omitted changeover
    changeover = (
        db.query(ChangeoverMatrix)
        .order_by(ChangeoverMatrix.id)
        .first()
    )

    changeover_machine = (
        db.query(Machine)
        .filter_by(id=changeover.machine_id)
        .first()
    )

    changeover_product = (
        db.query(Product)
        .filter_by(id=changeover.from_product_id)
        .first()
    )

    ground_truth.append({
        "case_id": "GT-005",
        "scenario": "omitted_changeover",
        "entity_id": changeover_machine.machine_code,
        "related_entity_id": changeover_product.product_code,
        "description": "A product transition is scheduled without applying the required changeover time.",
        "expected_violation": "Sequence-dependent changeover omitted"
    })

    # Save JSON file
    json_path = output_dir / "ground_truth.json"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(ground_truth, file, indent=4)

    # Save CSV file
    csv_path = output_dir / "ground_truth.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=ground_truth[0].keys()
        )
        writer.writeheader()
        writer.writerows(ground_truth)

    print("GROUND TRUTH CREATED SUCCESSFULLY!\n")

    for case in ground_truth:
        print(
            case["case_id"],
            "-",
            case["scenario"]
        )

    print("\nTotal labeled edge cases:", len(ground_truth))
    print("JSON:", json_path)
    print("CSV:", csv_path)

except Exception as error:
    print("ERROR:", error)
    raise

finally:
    db.close()
