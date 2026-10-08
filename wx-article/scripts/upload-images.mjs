#!/usr/bin/env node
// Upload an article's resources/ images to the image repo and rewrite content.md
// to point at the CDN. WeChat cannot render local paths, and API drafts reject
// third-party hotlinks, so every image must live on the CDN before publishing.
//
// Usage: node upload-images.mjs <articleDir> [--dry-run]
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";

const REPO = process.env.WX_IMAGE_REPO || "LingyiChen-AI/images";
const PROJECT = process.env.WX_IMAGE_PROJECT || "wx-content-cdn";
// openclaw deliberately blanks GITHUB_TOKEN/GH_TOKEN in the agent environment so a
// gateway GitHub credential cannot leak into agent-run commands. Read a dedicated
// name first, and keep GITHUB_TOKEN as the fallback for plain shell use.
const token = process.env.WX_GITHUB_TOKEN || process.env.GITHUB_TOKEN;

const argv = process.argv.slice(2);
const dryRun = argv.includes("--dry-run");
const articleDir = argv.find((a) => !a.startsWith("--"));
if (!articleDir) {
  console.error("usage: upload-images.mjs <articleDir> [--dry-run]");
  process.exit(2);
}
if (!token && !dryRun) {
  console.error("GITHUB_TOKEN not set");
  process.exit(2);
}

const parts = articleDir.replace(/\/+$/, "").split("/");
const title = parts[parts.length - 1];
const dateDir = parts[parts.length - 2];
const [yyyy, mm] = [dateDir.slice(0, 4), dateDir.slice(4, 6)];
const slug = createHash("md5").update(title).digest("hex").slice(0, 6);

const resources = join(articleDir, "resources");
let files = [];
try {
  files = readdirSync(resources).filter((f) => /\.(png|jpe?g|gif|webp)$/i.test(f)).sort();
} catch { /* no resources dir */ }

async function put(name) {
  const remote = `${PROJECT}/images/${yyyy}/${mm}/${dateDir}-${slug}-${name}`;
  const url = `https://api.github.com/repos/${REPO}/contents/${remote}`;
  const body = JSON.stringify({
    message: `upload: ${dateDir}-${slug}-${name}`,
    content: readFileSync(join(resources, name)).toString("base64"),
  });
  // GitHub throws transient 5xx/429 under sustained writes; back off and retry.
  for (let i = 0; i < 5; i++) {
    const res = await fetch(url, {
      method: "PUT",
      headers: { Authorization: `token ${token}`, "Content-Type": "application/json" },
      body,
    });
    if (res.ok) return `https://cdn.jsdelivr.net/gh/${REPO}/${remote}`;
    if (res.status === 422) {
      const cur = await fetch(url, { headers: { Authorization: `token ${token}` } }).then((r) => r.json());
      const retry = await fetch(url, {
        method: "PUT",
        headers: { Authorization: `token ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ...JSON.parse(body), sha: cur.sha }),
      });
      if (retry.ok) return `https://cdn.jsdelivr.net/gh/${REPO}/${remote}`;
    }
    if (![429, 500, 502, 503, 504].includes(res.status) || i === 4) {
      throw new Error(`${name}: HTTP ${res.status} ${(await res.text()).slice(0, 160)}`);
    }
    await new Promise((r) => setTimeout(r, 2000 * 2 ** i));
  }
}

const map = {};
for (const f of files) {
  if (dryRun) { map[`./resources/${f}`] = `https://cdn.jsdelivr.net/gh/${REPO}/${PROJECT}/images/${yyyy}/${mm}/${dateDir}-${slug}-${f}`; continue; }
  map[`./resources/${f}`] = await put(f);
  console.error(`  uploaded ${f}`);
}

const mdPath = join(articleDir, "content.md");
let md = readFileSync(mdPath, "utf8");
let replaced = 0;
for (const [local, cdn] of Object.entries(map)) {
  if (md.includes(local)) { md = md.split(local).join(cdn); replaced++; }
}
if (!dryRun && replaced) writeFileSync(mdPath, md, "utf8");

const leftover = [...md.matchAll(/\.\/resources\/[^\s)"']+/g)].map((m) => m[0]);
console.log(JSON.stringify({
  articleDir, uploaded: Object.keys(map).length, rewritten: replaced,
  leftoverLocalRefs: [...new Set(leftover)], dryRun,
}, null, 2));
