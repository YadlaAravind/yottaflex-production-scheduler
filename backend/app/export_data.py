import os
import pandas as pd

from sqlalchemy import create_engine, text

DATABASE_URL = "sqlite:///./yottaflex_generated.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

OUTPUT_DIR = "../data/exports"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TABLES = [
    "products",
    "machines",
    "materials",
    "production_orders",
    "routings",
    "routing_steps",
    "machine_calendars",
    "operations",
    "operation_schedules",
    "inventory_lots",
    "operation_material_requirements",
    "changeover_matrix",
    "machine_downtime",
    "schedule_events",
]

with engine.connect() as connection:
    for table in TABLES:
        try:
            df = pd.read_sql(
                text(f'SELECT * FROM "{table}"'),
                connection
            )

            file_path = os.path.join(
                OUTPUT_DIR,
                f"{table}.csv"
            )

            df.to_csv(file_path, index=False)

            print(f"Exported {table}: {len(df)} rows")

        except Exception as error:
            print(f"Could not export {table}: {error}")

print("\nCSV export completed!")