// Spidey Sense web dashboard – talks to the running app on 127.0.0.1.
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="spidey-token"]').content;
  const POLL_MS = 3000;
  const $ = (id) => document.getElementById(id);

  let tasks = [];
  let editing = null;
  let polling = null;
  let previewTimer = null;
  let undoTimer = null;

  // ---------------------------------------------------------------- API

  async function api(method, path, body) {
    const opts = { method, headers: { "X-Spidey-Token": TOKEN } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    setConnected(true);
    return data;
  }

  function setConnected(ok) {
    $("conn").className = "conn " + (ok ? "ok" : "bad");
    $("conn-text").textContent = ok ? "Spidey is live" : "Spidey isn't running";
  }

  // ---------------------------------------------------------------- render

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const child of children) node.append(child);
    return node;
  }

  function renderTasks(data) {
    tasks = data.tasks;
    $("count").textContent = tasks.length;
    $("empty").hidden = tasks.length > 0;
    const list = $("tasks");
    list.replaceChildren(...tasks.map(taskRow));
    if (!data.can_undo) hideUndo();
  }

  function taskRow(task) {
    const meta = [];
    if (task.deadline_label) meta.push((task.overdue ? "⚠ " : "📅 ") + task.deadline_label);
    if (task.snoozed_until) meta.push("💤 snoozed");
    if (task.notes) meta.push("📝");
    const cls = "task" + (task.overdue ? " overdue" : task.due_soon ? " soon" : "");
    const row = el("li", { class: cls, "data-id": task.id },
      el("button", { class: "check", title: "Mark done", "aria-label": `Mark “${task.title}” done`,
                     onclick: () => complete(task, row) }),
      el("span", { class: "prio-dot " + task.priority, title: task.priority + " priority" }),
      el("div", { class: "task-main" },
        el("div", { class: "task-title" }, task.title),
        el("div", { class: "task-meta" }, meta.join(" · "))),
      el("div", { class: "task-actions" },
        el("button", { class: "icon-btn", title: "Focus on this", "aria-label": "Focus on this",
                       onclick: () => startFocus(task.id) }, "🎯"),
        el("button", { class: "icon-btn", title: "Snooze", "aria-label": "Snooze",
                       onclick: (e) => snoozeMenu(e, task) }, "💤"),
        el("button", { class: "icon-btn", title: "Edit", "aria-label": "Edit",
                       onclick: () => openEditor(task) }, "✎")));
    return row;
  }

  function renderStats(s) {
    $("s-streak").textContent = s.streak;
    $("s-today").textContent = s.done_today;
    $("s-week").textContent = s.done_week;
    $("s-focus").textContent = s.focus_today_min;
    const max = Math.max(1, ...s.daily_done);
    const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    $("bars").replaceChildren(...s.days.map((day, i) => {
      const n = s.daily_done[i];
      const label = names[new Date(day + "T12:00").getDay()];
      const bar = el("i");
      bar.style.height = `${(n / max) * 78}%`;
      return el("div", { class: "bar" + (i === s.days.length - 1 ? " today" : ""), title: `${n} on ${day}` },
        el("b", {}, n ? String(n) : ""), bar, label);
    }));
  }

  function fmt(seconds) {
    const m = Math.floor(seconds / 60), s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function renderFocus(f) {
    const running = f.state !== "idle";
    const card = document.querySelector(".focus");
    card.classList.toggle("break", f.state === "break");
    $("f-time").textContent = running ? fmt(f.remaining_s) : fmt(f.focus_minutes * 60);
    $("f-state").textContent = { idle: "Ready", focusing: "Focusing", break: "Break" }[f.state];
    $("f-task").textContent = f.task_title ? `🎯 ${f.task_title}` : "";
    const circumference = 326.73;
    $("ring-fill").style.strokeDashoffset = running ? circumference * (1 - f.progress) : circumference;
    $("f-btn").textContent = running ? (f.state === "break" ? "End break" : "Stop focus") : "Start focus";
    $("f-btn").dataset.running = running ? "1" : "";
  }

  // ---------------------------------------------------------------- actions

  async function refresh() {
    try {
      const state = await api("GET", "/api/state");
      renderTasks(state);
      renderStats(state.stats);
      renderFocus(state.focus);
    } catch (err) {
      setConnected(false);
    }
  }

  async function complete(task, row) {
    row.classList.add("leaving");
    await new Promise((r) => setTimeout(r, 450));
    try {
      renderTasks(await api("POST", `/api/tasks/${task.id}/complete`));
      showUndo();
      refresh();
    } catch (err) {
      row.classList.remove("leaving");
      alert(err.message);
    }
  }

  function showUndo() {
    $("undo").hidden = false;
    clearTimeout(undoTimer);
    undoTimer = setTimeout(hideUndo, 10000);
  }

  function hideUndo() {
    $("undo").hidden = true;
  }

  function closeMenus() {
    document.querySelectorAll(".menu").forEach((m) => m.remove());
  }

  function snoozeMenu(event, task) {
    event.stopPropagation();
    closeMenus();
    const choose = (minutes) => async () => {
      closeMenus();
      renderTasks(await api("POST", `/api/tasks/${task.id}/snooze`, { minutes }));
    };
    const menu = el("div", { class: "menu", role: "menu" },
      el("button", { onclick: choose(10) }, "10 minutes"),
      el("button", { onclick: choose(60) }, "1 hour"),
      el("button", { onclick: choose(-1) }, "Tomorrow 9:00"));
    const rect = event.currentTarget.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 4}px`;
    menu.style.left = `${Math.max(8, rect.right + window.scrollX - 150)}px`;
    document.body.append(menu);
  }

  async function startFocus(taskId) {
    renderFocus(await api("POST", "/api/focus/start", taskId == null ? {} : { task_id: taskId }));
  }

  function openEditor(task) {
    editing = task;
    $("e-title").value = task.title;
    $("e-notes").value = task.notes || "";
    $("e-due").value = task.deadline ? task.deadline.slice(0, 16) : "";
    document.querySelectorAll('input[name="prio"]').forEach((r) => { r.checked = r.value === task.priority; });
    $("editor").showModal();
  }

  // ---------------------------------------------------------------- wiring

  $("add-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("add-input");
    const text = input.value.trim();
    if (!text) return;
    try {
      renderTasks(await api("POST", "/api/tasks", { text }));
      input.value = "";
      $("preview").hidden = true;
    } catch (err) {
      alert(err.message);
    }
  });

  $("add-input").addEventListener("input", () => {
    clearTimeout(previewTimer);
    const text = $("add-input").value.trim();
    if (!text) { $("preview").hidden = true; return; }
    previewTimer = setTimeout(async () => {
      try {
        const p = await api("GET", "/api/parse?text=" + encodeURIComponent(text));
        const chips = [el("span", { class: "chip" }, p.title || "…")];
        if (p.deadline_label) chips.push(el("span", { class: "chip" }, "📅 " + p.deadline_label));
        if (p.priority !== "normal") chips.push(el("span", { class: "chip" }, "● " + p.priority));
        $("preview").replaceChildren(...chips);
        $("preview").hidden = false;
      } catch (_) { /* preview is optional */ }
    }, 180);
  });

  $("undo-btn").addEventListener("click", async () => {
    hideUndo();
    renderTasks(await api("POST", "/api/undo"));
    refresh();
  });

  $("f-btn").addEventListener("click", async () => {
    if ($("f-btn").dataset.running) renderFocus(await api("POST", "/api/focus/stop"));
    else startFocus(null);
  });

  $("edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!editing) return;
    const prio = document.querySelector('input[name="prio"]:checked');
    const due = $("e-due").value;
    try {
      renderTasks(await api("PATCH", `/api/tasks/${editing.id}`, {
        title: $("e-title").value,
        notes: $("e-notes").value,
        priority: prio ? prio.value : editing.priority,
        deadline: due ? due + ":00" : null,
      }));
      $("editor").close();
    } catch (err) {
      alert(err.message);
    }
  });
  $("e-cancel").addEventListener("click", () => $("editor").close());
  $("e-delete").addEventListener("click", async () => {
    if (!editing || !confirm(`Delete “${editing.title}”?`)) return;
    renderTasks(await api("DELETE", `/api/tasks/${editing.id}`));
    $("editor").close();
  });

  document.addEventListener("click", closeMenus);
  document.addEventListener("visibilitychange", () => {
    clearInterval(polling);
    if (!document.hidden) { refresh(); polling = setInterval(refresh, POLL_MS); }
  });

  refresh();
  polling = setInterval(refresh, POLL_MS);
})();
