import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";

async function formatPath(path) {
  const info = await stat(path);
  if (info.isDirectory()) {
    for (const entry of await readdir(path)) {
      await formatPath(join(path, entry));
    }
  } else if (info.isFile() && path.endsWith(".ts")) {
    const source = await readFile(path, "utf8");
    const formatted = source.replace(/[ \t]+$/gm, "").trimEnd() + "\n";
    if (formatted !== source) await writeFile(path, formatted);
  }
}

const directories = process.argv.slice(2);
if (directories.length === 0) {
  directories.push(fileURLToPath(new URL("../src/generated", import.meta.url)));
}
for (const directory of directories) {
  await formatPath(resolve(directory));
}
