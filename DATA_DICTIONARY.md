\# YottaFlex – Data Dictionary



\## 1. Overview



This document describes the database entities, columns, data types, constraints, and relationships defined in `backend/app/models.py`.



The database uses SQLAlchemy ORM with relational database constraints.



\## 2. Database Tables



\### 2.1 products



Stores manufactured product information.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| product\_code | String(50) | Unique, Not Null |

| name | String(100) | Not Null |

| description | String(255) | Nullable |

| created\_at | DateTime | Defaults to UTC creation time |



\### 2.2 machines



Stores manufacturing machine information.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| machine\_code | String(50) | Unique, Not Null |

| name | String(100) | Not Null |

| capacity | Float | Not Null |

| status | String(30) | Default: active |



\### 2.3 production\_orders



Stores production order details.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| order\_code | String(50) | Unique, Not Null |

| product\_id | Integer | FK → products.id, Not Null |

| quantity | Integer | Not Null |

| priority | String(20) | Default: normal |

| due\_date | DateTime | Not Null |

| status | String(30) | Default: pending |



Relationship: Each production order references one product.



\### 2.4 routings



Stores product manufacturing routing information.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| routing\_code | String(50) | Unique, Not Null |

| product\_id | Integer | FK → products.id, Not Null |

| version | Integer | Default: 1 |

| status | String(30) | Default: active |



Relationship: A routing contains multiple routing steps.



\### 2.5 routing\_steps



Stores individual manufacturing operations within a routing.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| routing\_id | Integer | FK → routings.id, Not Null |

| sequence\_number | Integer | Not Null |

| operation\_name | String(100) | Not Null |

| duration\_minutes | Integer | Not Null |



Relationship: Each routing step belongs to one routing and can be associated with multiple eligible machines.



\### 2.6 routing\_step\_machines



Bridge table implementing the many-to-many relationship between routing steps and machines.



| Column | Data Type | Constraints |

|---|---|---|

| routing\_step\_id | Integer | FK → routing\_steps.id, Composite Primary Key |

| machine\_id | Integer | FK → machines.id, Composite Primary Key |



Relationship:

\- One routing step can use multiple machines.

\- One machine can be eligible for multiple routing steps.

\- The combination of routing\_step\_id and machine\_id must be unique.



\### 2.7 machine\_calendars



Stores machine shift and availability information.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| machine\_id | Integer | FK → machines.id, Not Null |

| shift\_start | DateTime | Not Null |

| shift\_end | DateTime | Not Null |

| available\_minutes | Integer | Not Null |

| status | String(30) | Default: available |



Relationship: Each calendar record references one machine.



\### 2.8 materials



Stores raw material information.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| material\_code | String(50) | Unique, Not Null |

| name | String(100) | Not Null |

| unit | String(20) | Not Null |

| description | String(255) | Nullable |



\### 2.9 inventory\_lots



Stores material inventory lot details and availability.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| lot\_code | String(50) | Unique, Not Null |

| material\_id | Integer | FK → materials.id, Not Null |

| quantity | Float | Not Null |

| available\_at | DateTime | Not Null |

| expiry\_at | DateTime | Nullable |

| status | String(30) | Default: available |



Relationship: Each inventory lot references one material. A material can have multiple inventory lots.



\### 2.10 operations



Stores individual production operations associated with orders and routing steps.



| Column | Data Type | Constraints |

|---|---|---|

| id | Integer | Primary Key, Indexed |

| operation\_code | String(50) | Unique, Not Null |

| production\_order\_id | Integer | FK → production\_orders.id, Not Null |

| routing\_step\_id | Integer | FK → routing\_steps.id, Not Null |

| sequence\_number | Integer | Not Null |

| planned\_duration\_minutes | Integer | Not Null |

| status | String(30) | Default: pending |



Relationships:

\- Each operation references one production order.

\- Each operation references one routing step.

\- A production order can contain multiple operations.



\## 3. Relationship Summary



| Parent Entity | Child Entity | Relationship |

|---|---|---|

| Products | Production Orders | One-to-Many |

| Products | Routings | One-to-Many |

| Routings | Routing Steps | One-to-Many |

| Routing Steps | Machines | Many-to-Many through routing\_step\_machines |

| Machines | Machine Calendars | One-to-Many |

| Materials | Inventory Lots | One-to-Many |

| Production Orders | Operations | One-to-Many |

| Routing Steps | Operations | One-to-Many |



\## 4. Important Constraints



\- Primary keys uniquely identify database records.

\- Product, machine, order, routing, material, lot, and operation codes have unique constraints.

\- Foreign keys establish relationships between related entities.

\- Required fields are marked NOT NULL.

\- Optional fields allow NULL values.

\- Default statuses are defined in the SQLAlchemy models.



\## 5. Scope and Limitations



This dictionary documents the entities currently defined in `models.py`.



It does not assume that every entity mentioned in the project requirements is implemented as a database table.



For example, the current model file does not define dedicated tables for:

\- Operation material requirements

\- Operation schedules

\- Machine downtime

\- Changeover matrices

\- Scheduling event history



These entities may be implemented elsewhere in the project or may require further development.



\## 6. Source



Database model definitions:



`backend/app/models.py`
