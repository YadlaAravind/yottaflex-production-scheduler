
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Product,
    Machine,
    Material,
    InventoryLot,
    ProductionOrder,
    Routing,
    RoutingStep,
    MachineCalendar,
    Operation,
    OperationMaterialRequirement,
    ChangeoverMatrix
)

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
db = Session()

errors = []

try:
    print("STARTING DATA VALIDATION...\n")

    # 1. Check expected record counts
    expected_counts = {
        Product: 100,
        Machine: 40,
        Material: 200,
        ProductionOrder: 500,
        Operation: 2000,
        RoutingStep: 400,
        MachineCalendar: 200,
        OperationMaterialRequirement: 2000,
        ChangeoverMatrix: 120
    }

    for model, expected in expected_counts.items():
        actual = db.query(model).count()
        print(f"{model.__name__}: {actual}")

        if actual != expected:
            errors.append(
                f"{model.__name__}: expected {expected}, got {actual}"
            )

    # 2. Check primary and foreign key integrity
    with engine.connect() as connection:
        fk_errors = connection.exec_driver_sql(
            "PRAGMA foreign_key_check"
        ).fetchall()

    if fk_errors:
        errors.append(f"Foreign key violations: {fk_errors}")
    else:
        print("\nForeign key check: PASSED")

    # 3. Check routing step machine eligibility
    steps_without_machines = (
        db.query(RoutingStep)
        .filter(~RoutingStep.eligible_machines.any())
        .count()
    )

    print("Routing steps without eligible machines:", steps_without_machines)

    if steps_without_machines:
        errors.append("Some routing steps have no eligible machines")

    # 4. Check operations per order
    orders = db.query(ProductionOrder).all()

    for order in orders:
        if len(order.__dict__) == 0:
            pass

        operation_count = (
            db.query(Operation)
            .filter_by(production_order_id=order.id)
            .count()
        )

        if operation_count != 4:
            errors.append(
                f"Order {order.order_code} has {operation_count} operations"
            )

    print("Production order operation check: completed")

    # 5. Check operation and routing product consistency
    operations = db.query(Operation).all()

    for operation in operations:
        order = operation.production_order
        step = operation.routing_step
        routing = step.routing

        if order.product_id != routing.product_id:
            errors.append(
                f"Product mismatch in operation {operation.operation_code}"
            )

        if operation.planned_duration_minutes <= 0:
            errors.append(
                f"Invalid duration in {operation.operation_code}"
            )

    print("Operation routing consistency: checked")

    # 6. Check material quantities
    invalid_requirements = (
        db.query(OperationMaterialRequirement)
        .filter(OperationMaterialRequirement.quantity_required <= 0)
        .count()
    )

    if invalid_requirements:
        errors.append("Invalid material requirement quantities")

    print("Material requirement check: completed")

    # 7. Check inventory quantities
    invalid_inventory = (
        db.query(InventoryLot)
        .filter(InventoryLot.quantity < 0)
        .count()
    )

    if invalid_inventory:
        errors.append("Negative inventory quantities found")

    print("Inventory quantity check: completed")

    # Final result
    print("\n------------------------------")

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print("-", error)
    else:
        print("ALL VALIDATION CHECKS PASSED!")

    print("------------------------------")

except Exception as error:
    print("VALIDATION ERROR:", error)
    raise

finally:
    db.close()
