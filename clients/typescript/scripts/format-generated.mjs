import { readdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

async function formatDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await formatDirectory(path);
    } else if (entry.isFile() && entry.name.endsWith(".ts")) {
      const source = await readFile(path, "utf8");
      const formatted = source.replace(/[ \t]+$/gm, "");
      if (formatted !== source) await writeFile(path, formatted);
    }
  }
}

await formatDirectory(fileURLToPath(new URL("../src/generated", import.meta.url)));
