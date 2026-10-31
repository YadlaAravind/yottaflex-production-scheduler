
import random
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models

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


# Fixed seed: same input produces same dataset
SEED = 20261022
rng = random.Random(SEED)

# Separate database for generated dataset
DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
db = Session()

BASE_DATE = datetime(2026, 11, 1, 8, 0)

try:
    # Rebuild only the generated database
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    print("Generating manufacturing dataset...")

    # 1. Generate 40 machines
    machines = []

    for i in range(1, 41):
        machines.append(
            Machine(
                machine_code=f"MACH-{i:03d}",
                name=f"CNC Machine {i:03d}",
                capacity=float(rng.randint(80, 150)),
                status="active"
            )
        )

    db.add_all(machines)
    db.flush()

    # 2. Generate 200 materials
    materials = []

    for i in range(1, 201):
        materials.append(
            Material(
                material_code=f"MAT-2026-{i:06d}",
                name=f"Raw Material {i:03d}",
                unit="kg",
                description="Generated manufacturing material"
            )
        )

    db.add_all(materials)
    db.flush()

    # 3. Generate inventory lots
    inventory_lots = []

    for i, material in enumerate(materials, start=1):
        inventory_lots.append(
            InventoryLot(
                lot_code=f"LOT-2026-{i:06d}",
                material_id=material.id,
                quantity=float(rng.randint(5000, 10000)),
                available_at=BASE_DATE,
                status="available"
            )
        )

    db.add_all(inventory_lots)

    # 4. Generate 100 products and their routings
    products = []
    routing_steps_by_product = {}

    operation_names = [
        "Cutting",
        "Drilling",
        "Milling",
        "Finishing"
    ]

    for i in range(1, 101):
        product = Product(
            product_code=f"PROD-2026-{i:06d}",
            name=f"Manufactured Product {i:03d}",
            description="Generated manufacturing product"
        )

        db.add(product)
        db.flush()
        products.append(product)

        routing = Routing(
            routing_code=f"ROUTE-PROD-{i:06d}-01",
            product_id=product.id,
            version=1,
            status="active"
        )

        db.add(routing)
        db.flush()

        steps = []

        for sequence, operation_name in enumerate(
            operation_names, start=1
        ):
            step = RoutingStep(
                routing_id=routing.id,
                sequence_number=sequence,
                operation_name=operation_name,
                duration_minutes=rng.randint(20, 90)
            )

            db.add(step)
            db.flush()

            # Each step can run on two eligible machines
            step.eligible_machines = rng.sample(machines, 2)

            steps.append(step)

        routing_steps_by_product[product.id] = steps

    # 5. Generate machine calendars (5 shifts per machine)
    calendars = []

    for machine in machines:
        for day in range(5):
            shift_start = BASE_DATE + timedelta(days=day)
            shift_end = shift_start + timedelta(hours=8)

            calendars.append(
                MachineCalendar(
                    machine_id=machine.id,
                    shift_start=shift_start,
                    shift_end=shift_end,
                    available_minutes=480,
                    status="available"
                )
            )

    db.add_all(calendars)

    # 6. Generate 500 production orders
    orders = []

    for i in range(1, 501):
        product = rng.choice(products)

        orders.append(
            ProductionOrder(
                order_code=f"ORD-2026-{i:06d}",
                product_id=product.id,
                quantity=rng.randint(50, 500),
                priority=rng.choice(
                    ["normal", "normal", "high", "urgent"]
                ),
                due_date=BASE_DATE + timedelta(
                    days=rng.randint(2, 20)
                ),
                status="pending"
            )
        )

    db.add_all(orders)
    db.flush()

    # 7. Generate 2,000 operations (4 per order)
    operations = []
    requirements = []

    for order_number, order in enumerate(orders, start=1):
        steps = routing_steps_by_product[order.product_id]

        for sequence, step in enumerate(steps, start=1):
            operation_number = (order_number - 1) * 4 + sequence

            operation = Operation(
                operation_code=f"OP-2026-{operation_number:06d}",
                production_order_id=order.id,
                routing_step_id=step.id,
                sequence_number=sequence,
                planned_duration_minutes=step.duration_minutes,
                status="pending"
            )

            db.add(operation)
            db.flush()
            operations.append(operation)

            material = rng.choice(materials)

            requirements.append(
                OperationMaterialRequirement(
                    operation_id=operation.id,
                    material_id=material.id,
                    quantity_required=float(rng.randint(1, 10)),
                    unit=material.unit
                )
            )

    db.add_all(requirements)

    # 8. Generate sequence-dependent changeovers
    changeovers = []

    for machine in machines:
        for _ in range(3):
            from_product, to_product = rng.sample(products, 2)

            changeovers.append(
                ChangeoverMatrix(
                    machine_id=machine.id,
                    from_product_id=from_product.id,
                    to_product_id=to_product.id,
                    changeover_minutes=rng.randint(10, 60)
                )
            )

    db.add_all(changeovers)

    db.commit()

    print("\nDATA GENERATION SUCCESSFUL!")
    print("Random seed:", SEED)
    print("Products:", db.query(Product).count())
    print("Machines:", db.query(Machine).count())
    print("Materials:", db.query(Material).count())
    print("Production Orders:", db.query(ProductionOrder).count())
    print("Operations:", db.query(Operation).count())
    print("Routing Steps:", db.query(RoutingStep).count())
    print("Machine Calendars:", db.query(MachineCalendar).count())
    print(
        "Material Requirements:",
        db.query(OperationMaterialRequirement).count()
    )
    print("Changeovers:", db.query(ChangeoverMatrix).count())

    print("\nDatabase: yottaflex_generated.db")

except Exception as error:
    db.rollback()
    print("DATA GENERATION FAILED:", error)
    raise

finally:
    db.close()
