import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const sourceRoot = process.argv[2];
if (!sourceRoot) throw new Error("Expected PyTorch PH source directory");
const configPath = resolve(sourceRoot, "apps/pages-demo/next.config.mjs");
const config = await readFile(configPath, "utf8");
const anchor = '  output: "export",';
if (config.split(anchor).length !== 2 || config.includes("basePath:")) {
  throw new Error("Unexpected PyTorch PH Pages config; review the pinned source before building");
}
await writeFile(configPath, config.replace(anchor, `${anchor}\n  basePath: "/pytorch-fit-system",`));
console.log("Configured PyTorch PH demo for /pytorch-fit-system");
