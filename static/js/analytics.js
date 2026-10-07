// Analytics charts — data comes from MongoDB aggregations (window.ANALYTICS / JSON API)
(() => {
  const PALETTE = ["#3b4fd8", "#12b3a6", "#f5a524", "#e5484d", "#6b46d9", "#0b8fb3", "#14955a", "#e06d10", "#d6409f", "#556079"];
  const STATUS_COLORS = { "Submitted": "#8a93a8", "Under Review": "#0dcaf0", "Assigned": "#3b4fd8", "In Progress": "#f5a524", "Reopened": "#e06d10",
                          "Resolved": "#14955a", "Rejected": "#e5484d", "Closed": "#212529" };
  const PRIORITY_COLORS = { Low: "#14955a", Medium: "#0b8fb3", High: "#e08a00", Critical: "#e5484d" };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = "#6b7489";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  const charts = {};
  const intAxis = { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#eef0f6" } };

  function draw(id, config) {
    charts[id]?.destroy();
    charts[id] = new Chart(document.getElementById(id), { ...config, options: { maintainAspectRatio: false, ...config.options } });
  }
  const keys = o => Object.keys(o), vals = o => Object.values(o);

  function render(d) {
    draw("chartTimeline", { type: "line", data: { labels: d.timeline.labels.map(s => s.slice(5)),
      datasets: [{ label: "Complaints", data: d.timeline.values, borderColor: "#3b4fd8", backgroundColor: "rgba(59,79,216,.12)",
                   fill: true, tension: .35, pointRadius: 3 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: intAxis, x: { grid: { display: false } } } } });

    draw("chartResolved", { type: "doughnut", data: { labels: ["Resolved", "Unresolved", "Rejected"],
      datasets: [{ data: [d.resolved, d.unresolved, d.rejected], backgroundColor: ["#14955a", "#f5a524", "#e5484d"], borderWidth: 0 }] },
      options: { cutout: "68%", plugins: { legend: { position: "bottom" } } } });

    draw("chartCategory", { type: "bar", data: { labels: keys(d.by_category),
      datasets: [{ label: "Complaints", data: vals(d.by_category), backgroundColor: PALETTE, borderRadius: 6 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: intAxis, x: { grid: { display: false } } } } });

    draw("chartStatus", { type: "doughnut", data: { labels: keys(d.by_status),
      datasets: [{ data: vals(d.by_status), backgroundColor: keys(d.by_status).map(s => STATUS_COLORS[s]), borderWidth: 0 }] },
      options: { cutout: "60%", plugins: { legend: { position: "right" } } } });

    draw("chartDepartment", { type: "bar", data: { labels: keys(d.by_department),
      datasets: [{ label: "Complaints", data: vals(d.by_department), backgroundColor: "#12b3a6", borderRadius: 6 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: intAxis, y: { grid: { display: false } } } } });

    draw("chartPriority", { type: "pie", data: { labels: keys(d.by_priority),
      datasets: [{ data: vals(d.by_priority), backgroundColor: keys(d.by_priority).map(p => PRIORITY_COLORS[p]), borderWidth: 0 }] },
      options: { plugins: { legend: { position: "right" } } } });

    draw("chartRatings", { type: "bar", data: { labels: ["1★", "2★", "3★", "4★", "5★"],
      datasets: [{ label: "Responses", data: d.feedback.distribution,
                   backgroundColor: ["#e5484d", "#f07c3a", "#f5a524", "#4cbf7f", "#14955a"], borderRadius: 6 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: intAxis, x: { grid: { display: false } } } } });

    const perf = d.performance.filter(r => r.sla !== null);
    draw("chartSla", { type: "bar", data: { labels: perf.map(r => r.department),
      datasets: [{ label: "SLA compliance %", data: perf.map(r => r.sla), borderRadius: 6,
                   backgroundColor: perf.map(r => r.sla >= 80 ? "#14955a" : r.sla >= 60 ? "#f5a524" : "#e5484d") }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.raw + "% within SLA" } } },
                 scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => v + "%" }, grid: { color: "#eef0f6" } },
                           x: { grid: { display: false } } } } });

    const rate = document.getElementById("resRate");
    if (rate) rate.textContent = d.resolution_rate + "%";
  }

  render(window.ANALYTICS);

  // Live refresh through the JSON endpoint (fetch API)
  document.getElementById("refreshCharts")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;
    try { render(await (await fetch(window.ANALYTICS_URL)).json()); }
    finally { btn.disabled = false; }
  });
})();
