
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Product, Machine, ProductionOrder, Routing, RoutingStep


db = SessionLocal()

try:
    # 1. Create Product
    product = Product(
        product_code="PROD-2026-000001",
        name="Steel Component",
        description="Sample manufacturing product"
    )
    db.add(product)
    db.flush()

    # 2. Create Machine
    machine = Machine(
        machine_code="MACH-001",
        name="CNC Machine",
        capacity=100.0,
        status="active"
    )
    db.add(machine)
    db.flush()

    # 3. Create Production Order
    order = ProductionOrder(
        order_code="ORD-2026-000001",
        product_id=product.id,
        quantity=100,
        priority="high",
        due_date=datetime.now() + timedelta(days=7),
        status="pending"
    )
    db.add(order)

    # 4. Create Routing
    routing = Routing(
        routing_code="ROUTE-PROD-2026-000001-01",
        product_id=product.id,
        version=1,
        status="active"
    )
    db.add(routing)
    db.flush()

    # 5. Create Routing Step
    step = RoutingStep(
        routing_id=routing.id,
        sequence_number=1,
        operation_name="Cutting",
        duration_minutes=30
    )
    db.add(step)

    db.commit()

    print("Sample manufacturing data inserted successfully!")
    print("Product ID:", product.id)
    print("Machine ID:", machine.id)
    print("Production Order ID:", order.id)
    print("Routing ID:", routing.id)
    print("Routing Step ID:", step.id)

except Exception as error:
    db.rollback()
    print("Error:", error)

finally:
    db.close()
