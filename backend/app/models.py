
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Machine(Base):
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    machine_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    capacity = Column(Float, nullable=False)
    status = Column(String(30), default="active")


class ProductionOrder(Base):
    __tablename__ = "production_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String(50), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    priority = Column(String(20), default="normal")
    due_date = Column(DateTime, nullable=False)
    status = Column(String(30), default="pending")

    product = relationship("Product")



from sqlalchemy import Table


# Many-to-many relationship:
# One routing step can use multiple machines.
# One machine can be used by multiple routing steps.

routing_step_machines = Table(
    "routing_step_machines",
    Base.metadata,
    Column(
        "routing_step_id",
        Integer,
        ForeignKey("routing_steps.id"),
        primary_key=True
    ),
    Column(
        "machine_id",
        Integer,
        ForeignKey("machines.id"),
        primary_key=True
    )
)


class Routing(Base):
    __tablename__ = "routings"

    id = Column(Integer, primary_key=True, index=True)
    routing_code = Column(String(50), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String(30), default="active")

    steps = relationship(
        "RoutingStep",
        back_populates="routing",
        cascade="all, delete-orphan"
    )


class RoutingStep(Base):
    __tablename__ = "routing_steps"

    id = Column(Integer, primary_key=True, index=True)
    routing_id = Column(Integer, ForeignKey("routings.id"), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    operation_name = Column(String(100), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    routing = relationship("Routing", back_populates="steps")

    eligible_machines = relationship(
        "Machine",
        secondary=routing_step_machines
    )


class MachineCalendar(Base):
    __tablename__ = "machine_calendars"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    shift_start = Column(DateTime, nullable=False)
    shift_end = Column(DateTime, nullable=False)
    available_minutes = Column(Integer, nullable=False)
    status = Column(String(30), default="available")



class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    unit = Column(String(20), nullable=False)
    description = Column(String(255), nullable=True)


class InventoryLot(Base):
    __tablename__ = "inventory_lots"

    id = Column(Integer, primary_key=True, index=True)
    lot_code = Column(String(50), unique=True, nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    available_at = Column(DateTime, nullable=False)
    expiry_at = Column(DateTime, nullable=True)
    status = Column(String(30), default="available")

    material = relationship("Material")



class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, index=True)
    operation_code = Column(String(50), unique=True, nullable=False)

    production_order_id = Column(
        Integer,
        ForeignKey("production_orders.id"),
        nullable=False
    )

    routing_step_id = Column(
        Integer,
        ForeignKey("routing_steps.id"),
        nullable=False
    )

    sequence_number = Column(Integer, nullable=False)
    planned_duration_minutes = Column(Integer, nullable=False)
    status = Column(String(30), default="pending")

    production_order = relationship("ProductionOrder")
    routing_step = relationship("RoutingStep")


class OperationSchedule(Base):
    __tablename__ = "operation_schedules"

    id = Column(Integer, primary_key=True, index=True)
    schedule_code = Column(String(50), unique=True, nullable=False)

    operation_id = Column(
        Integer,
        ForeignKey("operations.id"),
        nullable=False
    )

    machine_id = Column(
        Integer,
        ForeignKey("machines.id"),
        nullable=False
    )

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(30), default="scheduled")

    operation = relationship("Operation")
    machine = relationship("Machine")


class ChangeoverMatrix(Base):
    __tablename__ = "changeover_matrix"

    id = Column(Integer, primary_key=True, index=True)

    machine_id = Column(
        Integer,
        ForeignKey("machines.id"),
        nullable=False
    )

    from_product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    to_product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    changeover_minutes = Column(Integer, nullable=False)



class OperationMaterialRequirement(Base):
    __tablename__ = "operation_material_requirements"

    id = Column(Integer, primary_key=True, index=True)

    operation_id = Column(
        Integer,
        ForeignKey("operations.id"),
        nullable=False
    )

    material_id = Column(
        Integer,
        ForeignKey("materials.id"),
        nullable=False
    )

    quantity_required = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)

    operation = relationship("Operation")
    material = relationship("Material")


class MachineDowntime(Base):
    __tablename__ = "machine_downtime"

    id = Column(Integer, primary_key=True, index=True)

    machine_id = Column(
        Integer,
        ForeignKey("machines.id"),
        nullable=False
    )

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=False)
    status = Column(String(30), default="planned")

    machine = relationship("Machine")


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"

    id = Column(Integer, primary_key=True, index=True)

    operation_schedule_id = Column(
        Integer,
        ForeignKey("operation_schedules.id"),
        nullable=True
    )

    event_type = Column(String(50), nullable=False)
    description = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    schedule = relationship("OperationSchedule")
