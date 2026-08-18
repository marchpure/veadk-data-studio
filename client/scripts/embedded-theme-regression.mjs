import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const embeddedLayout = readFileSync(
  resolve(root, "src/components/EmbeddedLayout.tsx"),
  "utf8",
);
const indexCss = readFileSync(resolve(root, "src/index.css"), "utf8");
const mainApp = readFileSync(resolve(root, "src/App.tsx"), "utf8");

assert.match(
  embeddedLayout,
  /data-embedded-layout="knowledge-center"/,
  "embedded layout must expose the stable knowledge-center scope",
);
assert.match(embeddedLayout, /Sources/);
assert.match(embeddedLayout, /Data Models/);
assert.match(embeddedLayout, /Dashboards/);
assert.match(embeddedLayout, /Evaluation/);
assert.match(embeddedLayout, /Folders/);
assert.match(
  embeddedLayout,
  /href=\{state\.config\.embedUrl\}|to=\{tab\.to\}|Navigate to="sources"/,
);
assert.doesNotMatch(
  mainApp,
  /data-embedded-layout="knowledge-center"/,
  "standalone BYAAN app shell must not carry the embedded theme scope",
);

const embeddedBlockIndex = indexCss.indexOf('[data-embedded-layout="knowledge-center"]');
assert.ok(embeddedBlockIndex > 0, "embedded theme block missing");
const beforeEmbeddedBlock = indexCss.slice(0, embeddedBlockIndex);
const embeddedBlock = indexCss.slice(embeddedBlockIndex);

assert.match(embeddedBlock, /--kc-embed-bg:/);
assert.match(embeddedBlock, /--kc-embed-border:/);
assert.match(embeddedBlock, /color-scheme: dark/);
assert.doesNotMatch(
  embeddedBlock,
  /filter\s*:\s*invert|backdrop-filter|opacity\s*:\s*0\./,
  "embedded theme must not rely on broad filter/invert/opacity/blur tricks",
);
assert.doesNotMatch(
  beforeEmbeddedBlock,
  /--kc-embed-|data-embedded-layout="knowledge-center"/,
  "knowledge-center theme tokens must stay inside the embedded block",
);

console.log("embedded theme regression checks passed");
