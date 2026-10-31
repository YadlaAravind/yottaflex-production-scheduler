\# YottaFlex – Production Scheduling System



\## 1. Project Overview



YottaFlex is a production scheduling application designed to assign manufacturing operations to available machines while considering production constraints.



The system provides a backend scheduling API and a React-based dashboard to monitor production schedules, machine utilization, scheduling progress, and unscheduled operations.



\## 2. Problem Statement



Manufacturing production planning involves multiple constraints:



\- Machine availability and downtime

\- Operation routing and precedence

\- Machine capacity

\- Sequence-dependent changeovers

\- Labor shifts and machine calendars

\- Material availability



The objective is to generate feasible schedules, identify operations that cannot be scheduled, and make scheduling decisions and exceptions visible.



\## 3. Technology Stack



\*\*Backend\*\*

\- Python

\- FastAPI

\- SQLAlchemy

\- SQLite



\*\*Frontend\*\*

\- React

\- Vite

\- JavaScript

\- Axios



\## 4. Project Structure



```text

yottaflex-production-scheduler/

│

├── backend/

│   ├── app/

│   ├── tests/

│   ├── validation\_output.txt

│   ├── repair\_validation\_output.txt

│   └── requirements.txt

│

├── frontend/

│   ├── src/

│   ├── public/

│   └── package.json

│

├── data/

│   ├── exports/

│   ├── analytics.json

│   ├── downtime\_conflicts.csv

│   ├── ground\_truth.csv

│   └── ground\_truth.json

│

└── README.md

```



\*The structure above highlights the main project areas. Additional files may exist.\*



\## 5. Setup and Execution



\### Backend



Open a terminal and navigate to the backend directory:



```powershell

cd backend

```



Activate the Python virtual environment if one has been created.



Install dependencies:



```powershell

pip install -r requirements.txt

```



Start the backend:



```powershell

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

```



Backend API:



`http://127.0.0.1:8000`



Interactive API documentation:



`http://127.0.0.1:8000/docs`



\### Frontend



Open another terminal:



```powershell

cd frontend

npm install

npm run dev

```



Open the application:



`http://localhost:5173`



Ensure the backend is running before using the frontend.



\## 6. Main Features



\### Dashboard

\- Total operations

\- Scheduled and unscheduled operations

\- Scheduling completion percentage

\- Makespan

\- Machine utilization

\- Completed and late orders

\- Average order delay



\### Production Schedule

\- Displays scheduled operations

\- Provides schedule information by date

\- Shows machine-wise scheduling information



\### Machines

\- Displays machine information

\- Shows machine utilization



\### Unscheduled Operations

\- Displays operations that could not be scheduled

\- Shows exception categories

\- Helps identify scheduling failures



\## 7. API Endpoints



| Endpoint | Purpose |

|---|---|

| `GET /` | Root endpoint |

| `GET /health` | Health check |

| `GET /analytics` | Production analytics |

| `GET /orders` | Production order information |

| `GET /unscheduled` | Unscheduled operation information |

| `GET /schedule` | Production schedule information |



The schedule endpoint supports a limit parameter, for example:



`GET /schedule?limit=5000`



Refer to `/docs` for available parameters and response schemas.



\## 8. Current Verification Results



The following results were observed during local application verification:



| Metric | Observed result |

|---|---:|

| Total operations | 2,000 |

| Scheduled operations | 1,492 |

| Unscheduled operations | 508 |

| Scheduling completion | 74.6% |

| Machines | 40 |

| Makespan | 103.98 hours |

| Machine utilization | 81.67% |

| Completed orders | 301 |

| Late orders | 21 |

| Average delay | 27.55 hours |



The schedule API returned 1,492 records, and the unscheduled API returned 508 records.



\### Unscheduled Operation Categories



| Reason | Count |

|---|---:|

| No available slot | 199 |

| Previous operation failed | 309 |

| Total | 508 |



These are observed application results, not a claim that every scheduling constraint has been fully satisfied.



\## 9. Validation and Known Limitations



A validation report is available at:



`backend/validation\_output.txt`



The recorded validation run reported:



\- 1,492 scheduled operations

\- 508 unscheduled operations

\- 80 machine downtime records

\- 82 validation errors



The reported errors concern machine downtime conflicts.



A separate repair-candidate analysis is available at:



`backend/repair\_validation\_output.txt`



That analysis was read-only. It evaluated possible alternatives but did not apply schedule repairs.



Known limitations:



\- The current schedule has unresolved downtime conflicts.

\- Not all 508 unscheduled operations have been resolved.

\- Candidate alternatives require joint schedule evaluation to avoid conflicts between proposed assignments.

\- Machine capacity validation requires a clearly established capacity unit and interpretation.

\- Further end-to-end verification is needed for all constraint combinations.

### Experimental Repair Planners

The experimental global repair planner scripts are supporting analysis tools, not part of the main scheduling API workflow. They use a separate backup SQLite database (`yottaflex_generated_backup.db`) in read-only mode. This backup database is not included in the repository. These scripts will require a separately prepared backup database before they can run. The main application uses `yottaflex_generated.db` and does not depend on these experimental planners.

\## 10. Ground Truth Scenarios



The `data` directory contains ground-truth CSV and JSON files describing five scenario categories:



1\. Machine overlap

2\. Operation precedence violation

3\. Material unavailable at consumption time

4\. Operation outside shift calendar

5\. Omitted changeover



These files document expected violation scenarios. Their presence alone does not establish that all five anomalies have been injected and independently validated in the scheduling database.



\## 11. Future Improvements



\- Resolve downtime conflicts through global rescheduling.

\- Improve joint candidate selection.

\- Strengthen machine capacity validation.

\- Improve material allocation and availability checks.

\- Add comprehensive constraint-level tests.

\- Improve scheduling explanations and exception traceability.

\- Verify deterministic dataset generation and validation.



\## 12. Project Status



The application currently provides a working backend API, React dashboard, production schedule view, machine utilization view, and unscheduled-operation reporting.



The observed scheduling results and validation limitations are documented above to make the current implementation status transparent.
