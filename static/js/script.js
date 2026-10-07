// CampusFix — small UI helpers (no frameworks needed)
document.addEventListener("DOMContentLoaded", () => {
  // Mobile sidebar toggle
  const sidebar = document.getElementById("sidebar");
  document.getElementById("sidebarToggle")?.addEventListener("click", () => sidebar.classList.toggle("open"));
  document.getElementById("sidebarBackdrop")?.addEventListener("click", () => sidebar.classList.remove("open"));

  // Clickable table rows
  document.querySelectorAll("tr[data-href]").forEach(row =>
    row.addEventListener("click", e => { if (!e.target.closest("a,button")) window.location = row.dataset.href; }));

  // Auto-submit filter selects
  document.querySelectorAll("[data-autosubmit]").forEach(el => el.addEventListener("change", () => el.form.submit()));

  // Bootstrap client-side validation
  document.querySelectorAll("form.needs-validation").forEach(form =>
    form.addEventListener("submit", e => {
      if (!form.checkValidity()) { e.preventDefault(); e.stopPropagation(); }
      form.classList.add("was-validated");
    }));

  // Show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(btn => btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.togglePassword);
    input.type = input.type === "password" ? "text" : "password";
    btn.querySelector("i").className = input.type === "password" ? "bi bi-eye" : "bi bi-eye-slash";
  }));

  // Character counter
  document.querySelectorAll("[data-counter]").forEach(area => {
    const out = document.getElementById(area.dataset.counter);
    const update = () => out.textContent = `${area.value.length} / ${area.maxLength}`;
    area.addEventListener("input", update); update();
  });

  // File size check before upload
  document.querySelectorAll("input[type=file][data-max-mb]").forEach(input => input.addEventListener("change", () => {
    const f = input.files[0];
    if (f && f.size > input.dataset.maxMb * 1024 * 1024) {
      alert(`File is too large. Maximum size is ${input.dataset.maxMb} MB.`);
      input.value = "";
    }
  }));

  // Star rating label
  const ratingLabel = document.getElementById("ratingLabel");
  document.querySelectorAll(".star-input input").forEach(r => r.addEventListener("change", () => {
    if (ratingLabel && window.RATING_LABELS) ratingLabel.textContent = `${r.value} — ${window.RATING_LABELS[r.value]}`;
  }));

  // Department modal (create / edit)
  const modal = document.getElementById("deptModal");
  modal?.addEventListener("show.bs.modal", e => {
    const raw = e.relatedTarget?.dataset.dept;
    const d = raw ? JSON.parse(raw) : { name: "", description: "", categories: [] };
    document.getElementById("deptModalTitle").textContent = raw ? `Edit ${d.name}` : "New department";
    document.getElementById("deptOriginal").value = raw ? d.name : "";
    document.getElementById("deptName").value = d.name;
    document.getElementById("deptDesc").value = d.description;
    modal.querySelectorAll("input[name=categories]").forEach(cb => cb.checked = d.categories.includes(cb.value));
  });

  // Staff dropdown: show staff of the selected department first
  const dept = document.getElementById("deptSelect"), staff = document.getElementById("staffSelect");
  if (dept && staff) {
    const sortStaff = () => {
      const opts = [...staff.options].slice(1);
      opts.sort((a, b) => (b.dataset.dept === dept.value) - (a.dataset.dept === dept.value));
      opts.forEach(o => { staff.appendChild(o); o.textContent = o.textContent.replace(/^★ /, ""); if (o.dataset.dept === dept.value) o.textContent = "★ " + o.textContent; });
    };
    dept.addEventListener("change", sortStaff); sortStaff();
  }

  // Auto-hide success flashes
  setTimeout(() => document.querySelectorAll(".flash-stack .alert-success").forEach(a => bootstrap.Alert.getOrCreateInstance(a).close()), 5000);
});
