import { mkdir, copyFile, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("../../", import.meta.url));
const dest = path.join(root, "frontend/public/demo-assets");
await mkdir(dest, { recursive: true });
const map = {
  "identity.png": "demo-b-baseline-v1-original-0.png",
  "a.png": "demo-a-pose-2-v1-original-0.png",
};
const ids = [
  "0271e84ecb095e29a35cdfb46b121a0a",
  "2183d1aac32259fc8698cbd1dfbdf206",
  "26d0539544a8548ab90f7fac2b05aabc",
];
for (let p = 1; p <= 3; p++) {
  map[`pose-${p}.png`] = `demo-b-pose-${p}-v1-original-0.png`;
  map[`pose-${p}-alpha.png`] = `demo-b-pose-${p}-v1-alpha-transparent-0.png`;
}
for (const mood of ["happy", "surprised", "angry"]) {
  map[`${mood}.png`] = `acceptance-demo-b-${ids[1]}-${mood}-v1-original-0.png`;
  map[`${mood}-alpha.png`] =
    `acceptance-demo-b-${ids[1]}-${mood}-v1-alpha-transparent-0.png`;
}
const available = [];
for (const [name, source] of Object.entries(map)) {
  try {
    await copyFile(path.join(root, "samples", source), path.join(dest, name));
    available.push(name);
  } catch {
    console.warn(
      `Sample unavailable: ${source}. UI will show an explicit missing-image notice.`,
    );
  }
}
try {
  const bundle = JSON.parse(
    await readFile(path.join(root, "data/anima-hub.templates.json"), "utf8"),
  );
  await writeFile(path.join(dest, "catalog.json"), JSON.stringify(bundle));
} catch {
  await writeFile(
    path.join(dest, "catalog.json"),
    JSON.stringify({ schema_version: 1, templates: [] }),
  );
}
await writeFile(
  path.join(dest, "provenance.json"),
  JSON.stringify(
    {
      notice:
        "Historical samples, not results of prototype input. No inference performed.",
      files: map,
      available,
    },
    null,
    2,
  ),
);
console.log(
  `Prepared ${available.length} local historical samples. No API or GPU connection.`,
);
