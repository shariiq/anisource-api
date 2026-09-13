import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "../../");
const WEB_DIST = path.join(PROJECT_ROOT, "web", "dist");
const TARGET_STATIC_DIR = path.join(PROJECT_ROOT, "anime_extensions_api", "static", "app");

async function main() {
  console.log("Packaging AniSource SolidJS frontend...");

  // 1. Verify build output exists
  try {
    const stats = await fs.stat(WEB_DIST);
    if (!stats.isDirectory()) throw new Error("Not a directory");

    await fs.access(path.join(WEB_DIST, "index.html"));
  } catch (error) {
    console.error("❌ Build output not found. Did you run `npm run build`?");
    process.exit(1);
  }

  // 2. Prepare target directory
  try {
    const targetStats = await fs.stat(TARGET_STATIC_DIR);
    if (targetStats.isDirectory()) {
      console.log(`Clearing target directory: ${TARGET_STATIC_DIR}`);
      await fs.rm(TARGET_STATIC_DIR, { recursive: true, force: true });
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }

  console.log(`Creating target directory: ${TARGET_STATIC_DIR}`);
  await fs.mkdir(TARGET_STATIC_DIR, { recursive: true });

  // 3. Copy files recursively
  await fs.cp(WEB_DIST, TARGET_STATIC_DIR, { recursive: true });
  console.log("✅ Frontend assets copied to backend static directory successfully.");
}

main().catch(err => {
  console.error("❌ Error packaging frontend:", err);
  process.exit(1);
});
