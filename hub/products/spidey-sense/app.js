// Download buttons that know your OS, install tabs and copy buttons.
(() => {
  "use strict";

  const cfg = window.SPIDEY;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function detectOS() {
    const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    const ua = navigator.userAgent || "";
    const text = `${platform} ${ua}`.toLowerCase();
    if (/android|iphone|ipad|ipod/.test(text)) return "mobile";
    if (text.includes("win")) return "windows";
    if (text.includes("mac")) return "mac";
    if (text.includes("linux") || text.includes("x11") || text.includes("cros")) return "linux";
    return "unknown";
  }

  const url = (os) => `${cfg.RELEASE_BASE}/${cfg.FILES[os].file}`;
  const os = detectOS();
  const desktop = os in cfg.FILES;

  // Every [data-download="<os>"] link points at that OS's installer
  $$("[data-download]").forEach((a) => {
    const target = a.dataset.download === "auto" ? os : a.dataset.download;
    if (target in cfg.FILES) {
      a.href = url(target);
      a.setAttribute("download", "");
    }
  });
  $$("[data-note]").forEach((p) => { p.textContent = cfg.FILES[p.dataset.note].note; });

  // Hero button
  const primary = $("#dl-primary");
  if (desktop) {
    primary.href = url(os);
    primary.setAttribute("download", "");
    $("#dl-label").textContent = `Download for ${cfg.FILES[os].label}`;
    $("#dl-note").textContent = `v${cfg.VERSION} · ${cfg.FILES[os].note}`;
    const others = Object.keys(cfg.FILES).filter((k) => k !== os);
    $("#dl-others").replaceChildren(...others.flatMap((k, i) => {
      const a = document.createElement("a");
      a.href = "#install";
      a.textContent = cfg.FILES[k].label;
      a.addEventListener("click", () => selectTab(k));
      return i ? [" · ", a] : [a];
    }));
    // On Linux the one-line installer is the smoothest path
    if (os === "linux") {
      primary.href = "#install";
      primary.removeAttribute("download");
      $("#dl-label").textContent = "Install on Linux";
    }
  } else if (os === "mobile") {
    $("#dl-label").textContent = "Get it on your computer";
    $("#dl-note").textContent = "Spidey lives on desktops – open this page on your PC";
  }

  // Thank-you nudge after a download starts
  $$('a[download]').forEach((a) => a.addEventListener("click", () => {
    const note = $("#dl-note");
    if (a === primary && note) note.textContent = "Downloading… open the file when it's done 🕸";
  }));

  // Install tabs
  const tabs = $$('[role="tab"]');
  function selectTab(name) {
    tabs.forEach((t) => {
      const on = t.dataset.os === name;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      $(`#${t.getAttribute("aria-controls")}`).hidden = !on;
    });
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => selectTab(t.dataset.os));
    t.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      const next = tabs[(i + d + tabs.length) % tabs.length];
      selectTab(next.dataset.os);
      next.focus();
    });
  });
  selectTab(desktop ? os : "windows");

  // Copy buttons
  $$(".copy").forEach((button) => button.addEventListener("click", async () => {
    const text = $(`#${button.dataset.copy}`).textContent;
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents($(`#${button.dataset.copy}`));
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      document.execCommand("copy");
    }
    button.textContent = "Copied!";
    button.classList.add("done");
    setTimeout(() => { button.textContent = "Copy"; button.classList.remove("done"); }, 1800);
  }));

  // Footer + misc
  $("#version").textContent = cfg.VERSION;
  $("#dash-link").href = cfg.DASHBOARD_URL;
  for (const [id, href] of [["#gh-link", cfg.GITHUB], ["#li-link", cfg.LINKEDIN]]) {
    if (href) { $(id).href = href; $(id).hidden = false; }
  }
})();
