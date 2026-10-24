// Renders the app cards from catalog.js and wires the OS-aware download buttons.
(() => {
  "use strict";

  const hub = window.HUB;
  const os = hub.detectOS();
  const $ = (sel) => document.querySelector(sel);

  const ICONS = {
    windows: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 5.5 10.5 4.5v7H3v-6Zm8.5-1.1L21 3v8.5h-9.5V4.4ZM3 12.5h7.5v7L3 18.5v-6Zm8.5 0H21V21l-9.5-1.4v-7.1Z"/></svg>',
    linux: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2c-2.2 0-3.5 1.9-3.5 4.6 0 1.3.3 2.2-.3 3.4-.8 1.6-2.7 3.6-2.9 6.4-.1 1.3.4 2.3 1.2 2.9-.6.6-.6 1.6.3 2.1 1.1.6 2.6-.2 3.6-.2 1 0 1.3.8 2.6.8s1.6-.8 2.6-.8 2.5.8 3.6.2c.9-.5.9-1.5.3-2.1.8-.6 1.3-1.6 1.2-2.9-.2-2.8-2.1-4.8-2.9-6.4-.6-1.2-.3-2.1-.3-3.4C15.5 3.9 14.2 2 12 2Zm-1.6 4.2c.5 0 .8.6.8 1.2s-.3 1.1-.8 1.1-.8-.5-.8-1.1.4-1.2.8-1.2Zm3.2 0c.5 0 .8.6.8 1.2s-.3 1.1-.8 1.1-.8-.5-.8-1.1.4-1.2.8-1.2ZM12 9.4c.9 0 2 .6 2 1.1s-1.1 1.2-2 1.2-2-.7-2-1.2 1.1-1.1 2-1.1Z"/></svg>',
    mac: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M16.4 12.7c0-2.4 2-3.6 2.1-3.6-1.1-1.7-2.9-1.9-3.5-1.9-1.5-.2-2.9.9-3.7.9-.8 0-1.9-.9-3.2-.8-1.6 0-3.1 1-4 2.4-1.7 3-.4 7.4 1.2 9.8.8 1.2 1.8 2.5 3 2.4 1.2 0 1.7-.8 3.1-.8 1.5 0 1.9.8 3.2.8 1.3 0 2.1-1.2 2.9-2.4.9-1.4 1.3-2.7 1.3-2.8-.1 0-2.4-.9-2.4-4ZM14 5.6c.7-.8 1.1-1.9 1-3-1 0-2.1.6-2.8 1.4-.6.7-1.2 1.8-1 2.9 1 .1 2.1-.5 2.8-1.3Z"/></svg>',
  };

  // ---------------------------------------------------------- helpers

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v; // only used for our own static SVG icons
      else if (k === "style") node.style.cssText = v;
      else node.setAttribute(k, v);
    }
    node.append(...children.filter((c) => c != null));
    return node;
  }

  let toastTimer = null;
  function toast(product, osName) {
    const box = $("#toast");
    const file = product.downloads[osName].file;
    const hint = osName === "windows"
      ? ["Open ", el("b", {}, file), ". If Windows warns you, click ", el("b", {}, "More info → Run anyway"), "."]
      : osName === "mac"
        ? ["Open the .dmg, drag the app to Applications, then ", el("b", {}, "right-click → Open"), " the first time."]
        : ["Make it executable (right-click → Properties → ", el("b", {}, "Allow executing"), ") and double-click it."];
    box.replaceChildren(el("b", {}, `⬇ Downloading ${product.name}… `), ...hint);
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 9000);
  }

  function downloadLink(product, osName, cls, label) {
    const a = el("a", { class: cls, href: hub.downloadUrl(product, osName), download: "" });
    a.innerHTML = ICONS[osName];
    a.append(label || product.downloads[osName].label);
    a.addEventListener("click", () => toast(product, osName));
    return a;
  }

  // ---------------------------------------------------------- cards

  function liveCard(p) {
    const primaryOS = p.downloads[os] ? os : null;
    const others = Object.keys(p.downloads).filter((k) => k !== primaryOS);
    const buttons = el("div", { class: "dl-row" });
    if (primaryOS) {
      buttons.append(downloadLink(p, primaryOS, "btn btn-primary", `Download for ${p.downloads[primaryOS].label}`));
    }
    buttons.append(el("a", { class: "btn btn-glass", href: p.page }, "Details →"));
    const platforms = el("div", { class: "platforms" },
      ...others.map((k) => downloadLink(p, k, "btn btn-glass plat")));
    buttons.append(platforms);
    buttons.append(el("p", { class: "dl-meta" },
      `v${p.version}` + (primaryOS ? ` · ${p.downloads[primaryOS].note}` : " · free download")));

    return el("article", { class: "app", style: `--accent:${p.accent}` },
      el("div", { class: "app-top" },
        el("div", { class: "app-icon" }, el("img", { src: p.icon, alt: "", width: "70", height: "70" })),
        el("div", {},
          el("div", { class: "app-title" }, el("h3", {}, p.name), el("span", { class: `status ${p.status}` }, p.status)),
          el("div", { class: "cat" }, p.category))),
      el("p", { class: "tagline" }, p.tagline),
      el("p", { class: "desc" }, p.description),
      el("ul", { class: "chips" }, ...(p.highlights || []).map((h) => el("li", {}, h))),
      p.stats ? el("div", { class: "app-stats" },
        ...p.stats.map(([n, label]) => el("div", {}, el("b", {}, n), el("span", {}, label)))) : null,
      buttons);
  }

  function soonCard(p) {
    const contact = hub.email ? `mailto:${hub.email}` : hub.github;
    return el("article", { class: "app soon", style: `--accent:${p.accent}` },
      el("div", { class: "app-top" },
        el("div", { class: "app-icon placeholder" }, "🧪"),
        el("div", {},
          el("div", { class: "app-title" }, el("h3", {}, p.name), el("span", { class: "status soon" }, "Coming soon")),
          el("div", { class: "cat" }, p.category))),
      el("p", { class: "tagline" }, p.tagline),
      el("p", { class: "desc" }, p.description),
      contact ? el("div", {}, el("a", { class: "btn btn-glass", href: contact, target: "_blank", rel: "noopener" }, "Suggest an app")) : null);
  }

  $("#app-list").replaceChildren(...hub.products.map((p) => (p.status === "soon" ? soonCard(p) : liveCard(p))));

  // ---------------------------------------------------------- hero + spotlight buttons

  const flagship = hub.products.find((p) => p.status !== "soon");
  if (flagship && flagship.downloads[os]) {
    const btn = $("#hero-download");
    btn.href = hub.downloadUrl(flagship, os);
    btn.setAttribute("download", "");
    $("#hero-download-label").textContent = `Get ${flagship.name} for ${flagship.downloads[os].label}`;
    btn.addEventListener("click", () => toast(flagship, os));
  } else if (os === "mobile") {
    $("#hero-download-label").textContent = "Open on your computer to download";
  }
  document.querySelectorAll("[data-download]").forEach((a) => {
    const p = hub.product(a.dataset.download);
    if (p && p.downloads[os]) {
      a.href = hub.downloadUrl(p, os);
      a.setAttribute("download", "");
      a.textContent = `Download for ${p.downloads[os].label}`;
      a.addEventListener("click", () => toast(p, os));
    }
  });

  // ---------------------------------------------------------- owner details

  document.querySelectorAll("[data-hub]").forEach((n) => {
    const value = hub[n.dataset.hub];
    if (value) n.textContent = n.dataset.hub === "owner" && n.closest("h2") ? value.split(" ")[0] : value;
  });
  for (const [id, href] of [["#nav-github", hub.github], ["#about-github", hub.github],
                            ["#about-linkedin", hub.linkedin], ["#about-email", hub.email && `mailto:${hub.email}`]]) {
    const a = $(id);
    if (!a) continue;
    if (href) { a.href = href; a.hidden = false; } else { a.hidden = true; }
  }
  $("#year").textContent = new Date().getFullYear();
})();
