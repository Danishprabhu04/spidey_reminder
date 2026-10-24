// The app hub's catalog – the only file to edit when you add or update an app.
// Every page of the hub (and each product page) reads from here.
window.HUB = {
  owner: "Danish Prabhu",
  brand: "Danish Labs",
  tagline: "Small apps with big personality.",
  github: "https://github.com/Danishprabhu04",
  linkedin: "",
  email: "",

  products: [
    {
      id: "spidey-sense",
      name: "Spidey Sense",
      status: "live", // "live" | "beta" | "soon"
      version: "1.0.0", // keep in sync with src/hanging_reminder/__init__.py (CI checks it)
      category: "Productivity · Desktop companion",
      tagline: "Your friendly neighbourhood to-do list.",
      description:
        "A tiny Spidey hangs from the top of your screen on an elastic web, keeps your missions, " +
        "reminds you when something's due and celebrates every win with a backflip.",
      icon: "assets/spidey.png", // relative to the hub root
      accent: "#e23636",
      page: "products/spidey-sense/",
      screenshot: "assets/dashboard.webp",
      highlights: ["Elastic web physics", "Natural-language tasks", "Focus timer", "Web dashboard"],
      stats: [["16", "features"], ["3", "platforms"], ["0", "accounts needed"]],
      releaseBase: "https://github.com/Danishprabhu04/spidey_reminder/releases/latest/download",
      releasesPage: "https://github.com/Danishprabhu04/spidey_reminder/releases/latest",
      dashboardUrl: "http://127.0.0.1:47823/",
      downloads: {
        windows: { file: "SpideySense-Setup.exe", label: "Windows", note: "Windows 10 & 11 · 64-bit" },
        linux: { file: "SpideySense-x86_64.AppImage", label: "Linux", note: "Ubuntu 22.04+ and most 64-bit distros" },
        mac: { file: "SpideySense-macOS.dmg", label: "macOS", note: "macOS 12+ · Apple Silicon · beta" },
      },
    },
    {
      id: "next",
      name: "Something new",
      status: "soon",
      category: "In the lab",
      tagline: "The next app is being built.",
      description: "Got an idea for a tiny tool that would make your day better? Tell me – it might be next.",
      accent: "#3a6fe0",
    },
  ],
};

// Small helpers shared by the hub pages
window.HUB.detectOS = function detectOS() {
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  const text = `${platform} ${navigator.userAgent || ""}`.toLowerCase();
  if (/android|iphone|ipad|ipod/.test(text)) return "mobile";
  if (text.includes("win")) return "windows";
  if (text.includes("mac")) return "mac";
  if (text.includes("linux") || text.includes("x11") || text.includes("cros")) return "linux";
  return "unknown";
};
window.HUB.product = (id) => window.HUB.products.find((p) => p.id === id);
window.HUB.downloadUrl = (product, os) => `${product.releaseBase}/${product.downloads[os].file}`;
