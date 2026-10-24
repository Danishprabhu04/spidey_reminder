// Spidey on an elastic web – a small JS port of the desktop app's
// physics/elastic_rope.py (same constants), drawn on the hero canvas.
// Drag him by the invisible handle that follows him around, then let go.
(() => {
  "use strict";

  const GRAVITY = 1800;
  const WEB_STIFFNESS = 72;
  const LINEAR_DAMPING = 1.6;
  const TILT_STIFFNESS = 60;
  const TILT_DAMPING = 6.5;
  const TILT_FLING_KICK = 0.0015;
  const GRAB_STIFFNESS = 2500;
  const GRAB_DAMPING = 85;
  const RELEASE_SPEED_SCALE = 0.6;
  const MAX_RELEASE_SPEED = 1400;
  const DT = 1 / 120;

  const canvas = document.getElementById("web");
  if (!canvas || !canvas.getContext) return;
  const hero = canvas.parentElement;
  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const sprite = new Image();
  sprite.src = "assets/spidey.png";

  const handle = document.createElement("div");
  handle.setAttribute("aria-hidden", "true");
  Object.assign(handle.style, {
    position: "absolute", zIndex: 2, borderRadius: "50%", cursor: "grab", touchAction: "none",
  });
  hero.appendChild(handle);

  const s = {
    w: 0, h: 0, size: 150, anchor: { x: 0, y: 0 }, rest: 300,
    p: { x: 0, y: 0 }, v: { x: 0, y: 0 }, tilt: 0, tiltV: 0,
    grab: null, history: [], time: 0, running: true, last: 0, acc: 0,
  };

  function layout() {
    const rect = hero.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    s.w = rect.width;
    s.h = rect.height;
    canvas.width = Math.round(s.w * dpr);
    canvas.height = Math.round(s.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const narrow = s.w < 640;
    s.size = narrow ? 110 : Math.min(170, Math.max(130, s.w * 0.12));
    const oldAnchorX = s.anchor.x;
    s.anchor = { x: narrow ? s.w * 0.5 : s.w * 0.76, y: 0 };
    s.rest = narrow ? 120 : Math.min(s.h * 0.42, 320);
    if (!oldAnchorX) {  // first layout: start pulled to the side for a nice swing-in
      s.p = { x: s.anchor.x - (narrow ? 80 : 160), y: s.rest * 0.7 };
    } else {
      s.p.x += s.anchor.x - oldAnchorX;
    }
  }

  // ------------------------------------------------------------- physics

  function step(dt) {
    s.time += dt;
    let ax = 0, ay = GRAVITY;
    const dx = s.p.x - s.anchor.x, dy = s.p.y - s.anchor.y;
    const dist = Math.hypot(dx, dy) || 1e-6;
    const stretch = dist - s.rest;
    if (stretch > 0) {  // a web only pulls, it never pushes
      ax -= WEB_STIFFNESS * stretch * dx / dist;
      ay -= WEB_STIFFNESS * stretch * dy / dist;
    }
    ax -= LINEAR_DAMPING * s.v.x;
    ay -= LINEAR_DAMPING * s.v.y;
    if (!reduceMotion && !s.grab) ax += 22 * Math.sin(s.time * 0.9);  // idle sway
    if (s.grab) {
      ax += GRAB_STIFFNESS * (s.grab.x - s.p.x) - GRAB_DAMPING * s.v.x;
      ay += GRAB_STIFFNESS * (s.grab.y - s.p.y) - GRAB_DAMPING * s.v.y;
    }
    s.v.x += ax * dt;
    s.v.y += ay * dt;
    s.p.x += s.v.x * dt;
    s.p.y += s.v.y * dt;

    // He hangs head-down, so his body follows the web direction
    const ropeAngle = Math.atan2(-(s.p.x - s.anchor.x), s.p.y - s.anchor.y);
    const tiltA = -TILT_STIFFNESS * (s.tilt - ropeAngle) - TILT_DAMPING * s.tiltV;
    s.tiltV += tiltA * dt;
    s.tilt += s.tiltV * dt;

    // Bounce off the hero's edges
    const r = s.size * 0.55;
    if (s.p.x < r) { s.p.x = r; s.v.x = Math.abs(s.v.x) * 0.5; }
    if (s.p.x > s.w - r) { s.p.x = s.w - r; s.v.x = -Math.abs(s.v.x) * 0.5; }
    if (s.p.y > s.h - s.size) { s.p.y = s.h - s.size; s.v.y = -Math.abs(s.v.y) * 0.5; }
    if (s.p.y < 4) { s.p.y = 4; s.v.y = Math.abs(s.v.y) * 0.5; }
  }

  // ------------------------------------------------------------- drawing

  function draw() {
    ctx.clearRect(0, 0, s.w, s.h);
    const dx = s.p.x - s.anchor.x, dy = s.p.y - s.anchor.y;
    const dist = Math.hypot(dx, dy);
    const slack = Math.max(0, s.rest - dist);

    // The web: a soft glow + a crisp strand that sags when slack
    const midX = (s.anchor.x + s.p.x) / 2, midY = (s.anchor.y + s.p.y) / 2 + slack * 0.6;
    for (const [width, color] of [[6, "rgba(255,255,255,0.08)"], [1.6, "rgba(235,238,245,0.9)"]]) {
      ctx.beginPath();
      ctx.moveTo(s.anchor.x, s.anchor.y);
      ctx.quadraticCurveTo(midX, midY, s.p.x, s.p.y);
      ctx.lineWidth = width;
      ctx.strokeStyle = color;
      ctx.stroke();
    }

    // Spidey – the sprite's top edge is his feet, where the web attaches
    if (sprite.complete && sprite.naturalWidth) {
      ctx.save();
      ctx.translate(s.p.x, s.p.y);
      ctx.rotate(s.tilt);
      const squash = 1 + Math.max(-0.08, Math.min(0.12, (dist - s.rest) / 900));
      ctx.scale(1 / Math.sqrt(squash), squash);
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 18;
      ctx.shadowOffsetY = 10;
      ctx.drawImage(sprite, -s.size / 2, -s.size * 0.04, s.size, s.size);
      ctx.restore();
    }

    // Keep the drag handle over his body
    const cx = s.p.x - Math.sin(s.tilt) * s.size * 0.55;
    const cy = s.p.y + Math.cos(s.tilt) * s.size * 0.55;
    const hs = s.size * 0.8;
    handle.style.width = handle.style.height = `${hs}px`;
    handle.style.transform = `translate(${cx - hs / 2}px, ${cy - hs / 2}px)`;
    handle.style.left = handle.style.top = "0";
  }

  function frame(now) {
    if (!s.running) return;
    const elapsed = Math.min(0.05, (now - (s.last || now)) / 1000);
    s.last = now;
    s.acc += elapsed;
    while (s.acc >= DT) { step(DT); s.acc -= DT; }
    draw();
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------- input

  function local(e) {
    const rect = hero.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top, t: performance.now() };
  }

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    s.grab = local(e);
    s.history = [s.grab];
    handle.style.cursor = canvas.style.cursor = "grabbing";
    hero.classList.add("dragging");
  });
  handle.addEventListener("pointermove", (e) => {
    if (!s.grab) return;
    s.grab = local(e);
    s.history.push(s.grab);
    if (s.history.length > 6) s.history.shift();
  });
  const release = () => {
    if (!s.grab) return;
    // Fling with the pointer's recent velocity, tamed like the desktop app
    const first = s.history[0], last = s.history[s.history.length - 1];
    const dt = Math.max(0.016, (last.t - first.t) / 1000);
    let vx = (last.x - first.x) / dt * RELEASE_SPEED_SCALE;
    let vy = (last.y - first.y) / dt * RELEASE_SPEED_SCALE;
    const speed = Math.hypot(vx, vy);
    if (speed > MAX_RELEASE_SPEED) { vx *= MAX_RELEASE_SPEED / speed; vy *= MAX_RELEASE_SPEED / speed; }
    s.v = { x: vx, y: vy };
    s.tiltV += vx * TILT_FLING_KICK * 4;
    s.grab = null;
    handle.style.cursor = "grab";
    hero.classList.remove("dragging");
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);

  // Pause while the hero is off screen
  new IntersectionObserver(([entry]) => {
    const visible = entry.isIntersecting;
    if (visible && !s.running) { s.running = true; s.last = 0; requestAnimationFrame(frame); }
    s.running = visible;
  }).observe(hero);

  window.addEventListener("resize", layout);
  layout();
  requestAnimationFrame(frame);
})();
