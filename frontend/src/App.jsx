
import { useEffect, useState } from "react";
import axios from "axios";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid
} from "recharts";
import {
  Factory,
  CalendarDays,
  Activity,
  Clock,
  AlertTriangle,
  CheckCircle,
  Search,
  ChevronLeft,
  ChevronRight,
  ClipboardList
} from "lucide-react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [orders, setOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");

  const [schedules, setSchedules] = useState([]);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleError, setScheduleError] = useState("");
  const [selectedScheduleDate, setSelectedScheduleDate] = useState("");
  const [machineFilter, setMachineFilter] = useState("All");

  const [unscheduledEvents, setUnscheduledEvents] = useState([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState("");

  const [activePage, setActivePage] = useState("Dashboard");

  const [searchTerm, setSearchTerm] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const [currentPage, setCurrentPage] = useState(1);

  const [eventSearch, setEventSearch] = useState("");
  const [reasonFilter, setReasonFilter] = useState("All");
  const [eventPage, setEventPage] = useState(1);

  // Load dashboard analytics
  useEffect(() => {
    axios.get(`${API_URL}/analytics`)
      .then((response) => {
        setAnalytics(response.data);
        setLoading(false);
      })
      .catch((error) => {
        console.error("Analytics API error:", error);
        setError("Unable to load analytics. Check backend server.");
        setLoading(false);
      });
  }, []);

  // Load production orders
  useEffect(() => {
    if (activePage === "Production Schedule") {
      setOrdersLoading(true);
      setOrdersError("");

      axios.get(`${API_URL}/orders`)
        .then((response) => {
          if (Array.isArray(response.data)) {
            setOrders(response.data);
          } else {
            setOrders([]);
            setOrdersError("Invalid orders response from backend.");
          }
        })
        .catch((error) => {
          console.error("Orders API error:", error);
          setOrdersError("Unable to load production orders.");
          setOrders([]);
        })
        .finally(() => {
          setOrdersLoading(false);
        });
    }
  }, [activePage]);

  // Load production schedules
  useEffect(() => {
    if (activePage === "Production Schedule") {
      setScheduleLoading(true);
      setScheduleError("");

      axios.get(`${API_URL}/schedule?limit=5000`)
        .then((response) => {
          setSchedules(response.data.schedules || []);
        })
        .catch((error) => {
          console.error("Schedule API error:", error);
          setScheduleError(
            "Unable to load production schedule. Check backend server."
          );
        })
        .finally(() => {
          setScheduleLoading(false);
        });
    }
  }, [activePage]);

  // Load unscheduled events
  useEffect(() => {
    if (activePage === "Unscheduled Operations") {
      setEventsLoading(true);
      setEventsError("");

      axios.get(`${API_URL}/unscheduled?limit=2000`)
        .then((response) => {
          setUnscheduledEvents(response.data.events || []);
        })
        .catch((error) => {
          console.error("Unscheduled API error:", error);
          setEventsError("Unable to load unscheduled events.");
        })
        .finally(() => {
          setEventsLoading(false);
        });
    }
  }, [activePage]);

  if (loading) {
    return <div className="message">Loading dashboard...</div>;
  }

  if (error) {
    return <div className="message error">{error}</div>;
  }

  if (!analytics || analytics.error) {
    return (
      <div className="message error">
        {analytics?.error || "No analytics data available."}
      </div>
    );
  }

  // Machine utilization chart data
  const machineData = Object.entries(
    analytics.machine_utilization || {}
  ).map(([machine, utilization]) => ({
    machine: `M${machine.padStart(3, "0")}`,
    utilization
  }));

  // Schedule dates
  const scheduleDates = [
    ...new Set(
      schedules.map((item) => item.start_time.slice(0, 10))
    )
  ].sort();

  const activeScheduleDate =
    selectedScheduleDate || scheduleDates[0] || "";

  // Machine options
  const machineOptions = [
    ...new Map(
      schedules.map((item) => [
        item.machine_code,
        {
          code: item.machine_code,
          name: item.machine_name
        }
      ])
    ).values()
  ].sort((a, b) => a.code.localeCompare(b.code));

  // Daily schedules
  const dailySchedules = schedules.filter((item) => {
    const matchesDate =
      item.start_time.slice(0, 10) === activeScheduleDate;

    const matchesMachine =
      machineFilter === "All" ||
      item.machine_code === machineFilter;

    return matchesDate && matchesMachine;
  });

  const visibleMachines = machineOptions.filter(
    (machine) =>
      machineFilter === "All" || machine.code === machineFilter
  );

  // Timeline position
  const getTimelinePosition = (dateTime) => {
    const date = new Date(dateTime);
    return date.getHours() * 60 + date.getMinutes();
  };

  // Priority colors
  const getPriorityColor = (priority) => {
    const colors = {
      urgent: "#dc4545",
      high: "#e58b28",
      normal: "#4776e6",
      low: "#239b75"
    };

    return colors[priority?.toLowerCase()] || "#4776e6";
  };

  // Production order filtering
  const ordersPerPage = 10;

  const filteredOrders = orders.filter((order) => {
    const matchesSearch =
      `${order.order_code} ${order.product_name}`
        .toLowerCase()
        .includes(searchTerm.toLowerCase());

    const matchesPriority =
      priorityFilter === "All" ||
      order.priority?.toLowerCase() === priorityFilter.toLowerCase();

    return matchesSearch && matchesPriority;
  });

  const totalPages = Math.ceil(
    filteredOrders.length / ordersPerPage
  );

  const currentOrders = filteredOrders.slice(
    (currentPage - 1) * ordersPerPage,
    currentPage * ordersPerPage
  );

  // Unscheduled event filtering
  const eventsPerPage = 10;

  const filteredEvents = unscheduledEvents.filter((event) => {
    const matchesSearch =
      `${event.description || ""} ${event.reason || ""}`
        .toLowerCase()
        .includes(eventSearch.toLowerCase());

    const matchesReason =
      reasonFilter === "All" ||
      event.reason === reasonFilter;

    return matchesSearch && matchesReason;
  });

  const eventTotalPages = Math.ceil(
    filteredEvents.length / eventsPerPage
  );

  const currentEvents = filteredEvents.slice(
    (eventPage - 1) * eventsPerPage,
    eventPage * eventsPerPage
  );

  // Reason counts
  const reasonCounts = unscheduledEvents.reduce(
    (counts, event) => {
      counts[event.reason] =
        (counts[event.reason] || 0) + 1;

      return counts;
    },
    {}
  );

  // Reason cards
  const reasonCards = [
    {
      reason: "NO_AVAILABLE_SLOT",
      label: "No Available Slot",
      count: reasonCounts["NO_AVAILABLE_SLOT"] || 0,
      color: "orange"
    },
    {
      reason: "MATERIAL_UNAVAILABLE",
      label: "Material Unavailable",
      count: reasonCounts["MATERIAL_UNAVAILABLE"] || 0,
      color: "red"
    },
    {
      reason: "NO_ELIGIBLE_MACHINE",
      label: "No Eligible Machine",
      count: reasonCounts["NO_ELIGIBLE_MACHINE"] || 0,
      color: "purple"
    },
    {
      reason: "PREVIOUS_OPERATION_FAILED",
      label: "Previous Operation Failed",
      count: reasonCounts["PREVIOUS_OPERATION_FAILED"] || 0,
      color: "blue"
    }
  ];

  // Dashboard KPIs
  const kpis = [
    {
      title: "Total Operations",
      value: analytics.total_operations,
      icon: <Factory />,
      color: "blue"
    },
    {
      title: "Scheduled",
      value: analytics.scheduled_operations,
      icon: <CheckCircle />,
      color: "green"
    },
    {
      title: "Unscheduled",
      value: analytics.unscheduled_operations,
      icon: <AlertTriangle />,
      color: "orange"
    },
    {
      title: "Completion Rate",
      value: `${analytics.scheduling_completion_percentage}%`,
      icon: <Activity />,
      color: "purple"
    },
    {
      title: "Machine Utilization",
      value: `${analytics.overall_machine_utilization_percentage}%`,
      icon: <Factory />,
      color: "cyan"
    },
    {
      title: "Late Orders",
      value: analytics.late_orders,
      icon: <Clock />,
      color: "red"
    }
  ];

  // Format failure reason
  const formatReason = (reason) => {
    return (reason || "")
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  };

  // Format date
  const formatDate = (date) => {
    if (!date) return "N/A";
    return new Date(date).toLocaleString();
  };

  // Normalize order status
  const getOrderStatus = (order) => {
    if (order.status) return order.status;

    const total = order.total_operations ?? 0;
    const scheduled = order.scheduled_operations ?? 0;

    if (total === 0) return "No Operations";
    if (scheduled === total) return "Scheduled";
    if (scheduled > 0) return "Partially Scheduled";

    return "Unscheduled";
  };

  const getStatusClass = (status) => {
    return status.toLowerCase().replaceAll(" ", "-");
  };

  // Handle reason card click
  const handleReasonCardClick = (reason) => {
    setReasonFilter((currentReason) =>
      currentReason === reason ? "All" : reason
    );
    setEventPage(1);
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <Factory size={30} />
          <span>YottaFlex</span>
        </div>

        <p className="menu-label">MAIN MENU</p>

        <div
          className={`menu-item ${
            activePage === "Dashboard" ? "active" : ""
          }`}
          onClick={() => setActivePage("Dashboard")}
        >
          <Activity size={19} />
          Dashboard
        </div>

        <div
          className={`menu-item ${
            activePage === "Production Schedule" ? "active" : ""
          }`}
          onClick={() => setActivePage("Production Schedule")}
        >
          <CalendarDays size={19} />
          Production Schedule
        </div>

        <div
          className={`menu-item ${
            activePage === "Machines" ? "active" : ""
          }`}
          onClick={() => setActivePage("Machines")}
        >
          <Factory size={19} />
          Machines
        </div>

        <div
          className={`menu-item ${
            activePage === "Unscheduled Operations" ? "active" : ""
          }`}
          onClick={() => setActivePage("Unscheduled Operations")}
        >
          <ClipboardList size={19} />
          Unscheduled Operations
        </div>
      </aside>

      <main className="main-content">
        {/* Topbar */}
        <header className="topbar">
          <div>
            <h1>
              {activePage === "Dashboard"
                ? "Production Dashboard"
                : activePage}
            </h1>
            <p>Manufacturing operations overview</p>
          </div>

          <div className="status">
            <span className="status-dot"></span>
            System Online
          </div>
        </header>

        {/* Dashboard */}
        {activePage === "Dashboard" && (
          <>
            <section className="welcome">
              <div>
                <h2>Welcome to YottaFlex Scheduler</h2>
                <p>
                  Monitor production performance and scheduling efficiency.
                </p>
              </div>

              <Factory size={55} />
            </section>

            <section className="kpi-grid">
              {kpis.map((item) => (
                <div className="kpi-card" key={item.title}>
                  <div className={`kpi-icon ${item.color}`}>
                    {item.icon}
                  </div>

                  <p>{item.title}</p>
                  <h2>{item.value}</h2>
                </div>
              ))}
            </section>

            <section className="details-grid">
              <div className="panel">
                <h2>Machine Utilization</h2>

                <p className="panel-subtitle">
                  Utilization percentage across 40 machines
                </p>

                <div className="chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={machineData}>
                      <CartesianGrid strokeDasharray="3 3" />

                      <XAxis
                        dataKey="machine"
                        angle={-45}
                        textAnchor="end"
                        height={65}
                      />

                      <YAxis domain={[0, 100]} />
                      <Tooltip />

                      <Bar
                        dataKey="utilization"
                        fill="#4776e6"
                        radius={[5, 5, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="panel summary-panel">
                <h2>Production Summary</h2>

                <div className="summary-row">
                  <span>Makespan</span>
                  <strong>{analytics.makespan_hours} hours</strong>
                </div>

                <div className="summary-row">
                  <span>Fully Scheduled Orders</span>
                  <strong>{analytics.completed_orders}</strong>
                </div>

                <div className="summary-row">
                  <span>Average Delay</span>
                  <strong>{analytics.average_delay_hours} hours</strong>
                </div>

                <div className="summary-row">
                  <span>Total Machines</span>
                  <strong>{machineData.length}</strong>
                </div>

                <div className="summary-row">
                  <span>Unscheduled Operations</span>
                  <strong className="warning">
                    {analytics.unscheduled_operations}
                  </strong>
                </div>
              </div>
            </section>
          </>
        )}

        {/* Production Schedule */}
        {activePage === "Production Schedule" && (
          <>
            <section className="panel timeline-panel">
              <div className="timeline-heading">
                <div>
                  <h2>Machine Production Timeline</h2>

                  <p className="panel-subtitle">
                    Visual schedule of operations across available machines
                  </p>
                </div>

                <span className="timeline-total">
                  {dailySchedules.length} Scheduled Operations
                </span>
              </div>

              <div className="timeline-toolbar">
                <div>
                  <label>Schedule Date</label>

                  <select
                    value={activeScheduleDate}
                    onChange={(e) =>
                      setSelectedScheduleDate(e.target.value)
                    }
                  >
                    {scheduleDates.map((date) => (
                      <option value={date} key={date}>
                        {new Date(`${date}T00:00:00`).toLocaleDateString()}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label>Machine</label>

                  <select
                    value={machineFilter}
                    onChange={(e) => setMachineFilter(e.target.value)}
                  >
                    <option value="All">All Machines</option>

                    {machineOptions.map((machine) => (
                      <option value={machine.code} key={machine.code}>
                        {machine.code} - {machine.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="timeline-legend">
                <span>
                  <i style={{ background: "#dc4545" }} /> Urgent
                </span>
                <span>
                  <i style={{ background: "#e58b28" }} /> High
                </span>
                <span>
                  <i style={{ background: "#4776e6" }} /> Normal
                </span>
                <span>
                  <i style={{ background: "#239b75" }} /> Low
                </span>
              </div>

              {scheduleLoading ? (
                <p>Loading machine schedule...</p>
              ) : scheduleError ? (
                <p className="error">{scheduleError}</p>
              ) : scheduleDates.length === 0 ? (
                <p>No scheduled operations available.</p>
              ) : (
                <div className="timeline-scroll">
                  <div className="timeline-content">
                    <div className="timeline-header-row">
                      <div className="machine-label">Machine</div>

                      <div className="timeline-hours">
                        {Array.from({ length: 24 }, (_, hour) => (
                          <div className="timeline-hour" key={hour}>
                            {String(hour).padStart(2, "0")}:00
                          </div>
                        ))}
                      </div>
                    </div>

                    {visibleMachines.map((machine) => {
                      const machineSchedules = dailySchedules.filter(
                        (item) => item.machine_code === machine.code
                      );

                      return (
                        <div
                          className="machine-timeline-row"
                          key={machine.code}
                        >
                          <div className="machine-label">
                            <strong>{machine.code}</strong>
                            <span>{machine.name}</span>
                          </div>

                          <div className="machine-track">
                            {Array.from({ length: 24 }, (_, hour) => (
                              <div
                                className="hour-grid-line"
                                key={hour}
                                style={{
                                  left: `${(hour / 24) * 100}%`
                                }}
                              />
                            ))}

                            {machineSchedules.map((item) => {
                              const start = getTimelinePosition(
                                item.start_time
                              );

                              const end = getTimelinePosition(
                                item.end_time
                              );

                              const left = (start / 1440) * 100;

                              const width = Math.max(
                                ((end - start) / 1440) * 100,
                                0.5
                              );

                              return (
                                <div
                                  className="operation-block"
                                  key={item.schedule_id}
                                  title={`${item.operation_id} | ${item.product_name} | ${new Date(item.start_time).toLocaleTimeString()} - ${new Date(item.end_time).toLocaleTimeString()}`}
                                  style={{
                                    left: `${left}%`,
                                    width: `${width}%`,
                                    background: getPriorityColor(item.priority)
                                  }}
                                >
                                  <strong>{item.operation_id}</strong>
                                  <span>{item.operation_name}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {dailySchedules.length === 0 && (
                    <p className="timeline-empty">
                      No operations scheduled for this date and machine filter.
                    </p>
                  )}
                </div>
              )}
            </section>

            {/* Production Orders */}
            <section className="panel orders-panel">
              <h2>Production Orders</h2>

              <p className="panel-subtitle">
                Search, filter and view manufacturing orders
              </p>

              <div className="orders-toolbar">
                <div className="search-box">
                  <Search size={18} />

                  <input
                    type="text"
                    placeholder="Search order ID or product..."
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value);
                      setCurrentPage(1);
                    }}
                  />
                </div>

                <select
                  className="priority-select"
                  value={priorityFilter}
                  onChange={(e) => {
                    setPriorityFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                >
                  <option value="All">All Priorities</option>
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                </select>
              </div>

              <div className="orders-count">
                Showing {currentOrders.length} of {filteredOrders.length} orders
              </div>

              {ordersLoading ? (
                <p>Loading production orders...</p>
              ) : ordersError ? (
                <p className="error">{ordersError}</p>
              ) : (
                <>
                  <div className="table-container">
                    <table className="orders-table">
                      <thead>
                        <tr>
                          <th>Order ID</th>
                          <th>Product</th>
                          <th>Quantity</th>
                          <th>Priority</th>
                          <th>Due Date</th>
                          <th>Status / Progress</th>
                        </tr>
                      </thead>

                      <tbody>
                        {currentOrders.map((order) => {
                          const status = getOrderStatus(order);
                          const scheduled =
                            order.scheduled_operations ?? 0;
                          const total = order.total_operations ?? 0;

                          return (
                            <tr key={order.id}>
                              <td>{order.order_code}</td>
                              <td>{order.product_name}</td>
                              <td>{order.quantity}</td>

                              <td>
                                <span
                                  className={`priority ${order.priority?.toLowerCase()}`}
                                >
                                  {order.priority}
                                </span>
                              </td>

                              <td>
                                {new Date(order.due_date).toLocaleDateString()}
                              </td>

                              <td>
                                <span
                                  className={`status-badge ${getStatusClass(status)}`}
                                >
                                  {status}
                                </span>

                                <small className="operation-progress">
                                  {scheduled}/{total} operations
                                </small>
                              </td>
                            </tr>
                          );
                        })}

                        {currentOrders.length === 0 && (
                          <tr>
                            <td colSpan="6" className="empty-orders">
                              No matching orders found.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="pagination">
                    <span>
                      Page {totalPages === 0 ? 0 : currentPage} of {totalPages}
                    </span>

                    <div className="pagination-buttons">
                      <button
                        disabled={currentPage <= 1}
                        onClick={() =>
                          setCurrentPage((page) => Math.max(1, page - 1))
                        }
                      >
                        <ChevronLeft size={17} />
                        Previous
                      </button>

                      <button
                        disabled={
                          currentPage >= totalPages || totalPages === 0
                        }
                        onClick={() =>
                          setCurrentPage((page) =>
                            Math.min(totalPages, page + 1)
                          )
                        }
                      >
                        Next
                        <ChevronRight size={17} />
                      </button>
                    </div>
                  </div>
                </>
              )}
            </section>
          </>
        )}

        {/* Machines */}
        {activePage === "Machines" && (
          <section className="panel">
            <h2>Machine Overview</h2>

            <p className="panel-subtitle">
              Utilization across available machines
            </p>

            <div className="table-container">
              <table className="orders-table">
                <thead>
                  <tr>
                    <th>Machine ID</th>
                    <th>Utilization</th>
                  </tr>
                </thead>

                <tbody>
                  {machineData.map((machine) => (
                    <tr key={machine.machine}>
                      <td>{machine.machine}</td>
                      <td>{machine.utilization}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Unscheduled Operations */}
        {activePage === "Unscheduled Operations" && (
          <>
            <section className="unscheduled-heading">
              <div>
                <h2>Unscheduled Operations</h2>

                <p className="panel-subtitle">
                  Review operations that could not be assigned to a machine slot.
                </p>
              </div>

              <div className="unscheduled-total">
                <AlertTriangle size={20} />
                <strong>{unscheduledEvents.length}</strong>
                <span>Total Events</span>
              </div>
            </section>

            {eventsLoading ? (
              <div className="panel">
                Loading unscheduled operations...
              </div>
            ) : eventsError ? (
              <div className="panel message error">
                {eventsError}
              </div>
            ) : (
              <>
                {/* Clickable Reason Cards */}
                <section className="reason-grid">
                  {reasonCards.map((item) => (
                    <button
                      type="button"
                      className={`reason-card ${
                        reasonFilter === item.reason ? "selected" : ""
                      }`}
                      key={item.reason}
                      aria-pressed={reasonFilter === item.reason}
                      onClick={() => handleReasonCardClick(item.reason)}
                    >
                      <div className={`reason-icon ${item.color}`}>
                        <AlertTriangle size={20} />
                      </div>

                      <div className="reason-card-content">
                        <p>{item.label}</p>
                        <h2>{item.count}</h2>
                      </div>
                    </button>
                  ))}
                </section>

                {/* Unscheduled Event Details */}
                <section className="panel orders-panel">
                  <h2>Unscheduled Event Details</h2>

                  <p className="panel-subtitle">
                    Search operation IDs and filter by failure reason.
                  </p>

                  <div className="orders-toolbar">
                    <div className="search-box">
                      <Search size={18} />

                      <input
                        type="text"
                        placeholder="Search operation ID or description..."
                        value={eventSearch}
                        onChange={(e) => {
                          setEventSearch(e.target.value);
                          setEventPage(1);
                        }}
                      />
                    </div>

                    <select
                      className="priority-select"
                      value={reasonFilter}
                      onChange={(e) => {
                        setReasonFilter(e.target.value);
                        setEventPage(1);
                      }}
                    >
                      <option value="All">All Reasons</option>
                      <option value="NO_AVAILABLE_SLOT">
                        No Available Slot
                      </option>
                      <option value="MATERIAL_UNAVAILABLE">
                        Material Unavailable
                      </option>
                      <option value="NO_ELIGIBLE_MACHINE">
                        No Eligible Machine
                      </option>
                      <option value="PREVIOUS_OPERATION_FAILED">
                        Previous Operation Failed
                      </option>
                    </select>
                  </div>

                  <div className="orders-count">
                    Showing {currentEvents.length} of {filteredEvents.length} events
                  </div>

                  <div className="table-container">
                    <table className="orders-table">
                      <thead>
                        <tr>
                          <th>Event ID</th>
                          <th>Operation Details</th>
                          <th>Failure Reason</th>
                          <th>Description</th>
                          <th>Created At</th>
                        </tr>
                      </thead>

                      <tbody>
                        {currentEvents.map((event) => (
                          <tr key={event.event_id}>
                            <td>EVT-{event.event_id}</td>

                            <td>
                              {(event.description || "").split(":")[0]}
                            </td>

                            <td>
                              <span className="reason-badge">
                                {formatReason(event.reason)}
                              </span>
                            </td>

                            <td>
                              {(event.description || "")
                                .split(" - ")
                                .slice(1)
                                .join(" - ") || "No description"}
                            </td>

                            <td>{formatDate(event.created_at)}</td>
                          </tr>
                        ))}

                        {currentEvents.length === 0 && (
                          <tr>
                            <td colSpan="5" className="empty-orders">
                              No matching unscheduled events found.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Event Pagination */}
                  <div className="pagination">
                    <span>
                      Page {eventTotalPages === 0 ? 0 : eventPage} of {eventTotalPages}
                    </span>

                    <div className="pagination-buttons">
                      <button
                        disabled={eventPage <= 1}
                        onClick={() =>
                          setEventPage((page) => Math.max(1, page - 1))
                        }
                      >
                        <ChevronLeft size={17} />
                        Previous
                      </button>

                      <button
                        disabled={
                          eventPage >= eventTotalPages ||
                          eventTotalPages === 0
                        }
                        onClick={() =>
                          setEventPage((page) =>
                            Math.min(eventTotalPages, page + 1)
                          )
                        }
                      >
                        Next
                        <ChevronRight size={17} />
                      </button>
                    </div>
                  </div>
                </section>
              </>
            )}
          </>
        )}

        <footer>
          YottaFlex Production Scheduler · Powered by FastAPI and React
        </footer>
      </main>
    </div>
  );
}

export default App;
