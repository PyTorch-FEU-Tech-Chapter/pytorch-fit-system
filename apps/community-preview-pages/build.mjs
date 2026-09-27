import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import esbuild from "esbuild";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import loadConfig from "tailwindcss/loadConfig.js";
import autoprefixer from "autoprefixer";

const appDir = dirname(fileURLToPath(import.meta.url));
const repoDir = resolve(appDir, "../..");
const portalDir = resolve(repoDir, "apps/portal");
const outputDir = resolve(repoDir, "out/community-pages");
await mkdir(resolve(outputDir, "assets"), { recursive: true });

await esbuild.build({
  entryPoints: [resolve(appDir, "main.tsx")],
  outfile: resolve(outputDir, "assets/preview.js"),
  bundle: true,
  minify: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  jsx: "automatic",
  legalComments: "none",
  logLevel: "warning",
  plugins: [{
    name: "static-preview-shell",
    setup(build) {
      // The named demo component is reused; its unused Next page wrapper is not shipped.
      build.onResolve({ filter: /^@pytorch-fit\/domain-client\/navigation$/ }, () => ({ path: "shell", namespace: "static-preview" }));
      build.onLoad({ filter: /.*/, namespace: "static-preview" }, () => ({ contents: "export const AppShell = ({ children }) => children;" }));
    },
  }],
});

const bundledJs = await readFile(resolve(outputDir, "assets/preview.js"), "utf8");
if (/next\/router|next\/navigation|\/api\/|supabase\.co|discord\.com\/api/.test(bundledJs)) {
  throw new Error("Static preview unexpectedly contains a portal or external API dependency");
}

process.chdir(portalDir);
const sourceCss = await readFile(resolve(portalDir, "app/globals.css"), "utf8");
const themeConfig = loadConfig(resolve(portalDir, "tailwind.config.ts"));
const css = await postcss([
  tailwindcss({ ...themeConfig, content: [...themeConfig.content, resolve(appDir, "*.{html,tsx}").replaceAll("\\", "/")] }),
  autoprefixer(),
]).process(sourceCss, { from: resolve(portalDir, "app/globals.css"), to: resolve(outputDir, "assets/preview.css") });
await writeFile(resolve(outputDir, "assets/preview.css"), css.css);
await writeFile(resolve(outputDir, "index.html"), await readFile(resolve(appDir, "index.html")));
await writeFile(resolve(outputDir, ".nojekyll"), "");
console.log(`Community preview built at ${outputDir}`);
