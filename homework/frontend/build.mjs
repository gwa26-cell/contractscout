import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const assets = join(dist, "assets");
mkdirSync(assets, { recursive: true });

const files = [
  ["src/index.html", "index.html"],
  ["src/admin.html", "admin.html"],
  ["src/styles.css", "assets/styles.css"],
  ["src/admin.css", "assets/admin.css"],
  ["src/app.js", "assets/app.js"],
  ["src/admin.js", "assets/admin.js"],
  ["src/behavior-metrics.js", "assets/behavior-metrics.js"],
];

for (const [from, to] of files) {
  copyFileSync(join(root, from), join(dist, to));
}

console.log("build ok -> frontend/dist");
