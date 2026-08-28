import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const assets = join(dist, "assets");
mkdirSync(assets, { recursive: true });

copyFileSync(join(root, "src", "index.html"), join(dist, "index.html"));
copyFileSync(join(root, "src", "styles.css"), join(assets, "styles.css"));
copyFileSync(join(root, "src", "app.js"), join(assets, "app.js"));

console.log("build ok -> frontend/dist");
