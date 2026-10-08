#!/usr/bin/env node
// Scaffold one article directory per the project convention:
//   <root>/YYYYMMDD/<标题>/content.md + resources/
// Usage: node new-article.mjs "<标题>" [--root <dir>] [--date YYYYMMDD]
import { mkdirSync, existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const argv = process.argv.slice(2);
const flag = (n, d = null) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : d;
};
const title = argv.find((a) => !a.startsWith("--") && argv[argv.indexOf(a) - 1] !== "--root" && argv[argv.indexOf(a) - 1] !== "--date");
if (!title) {
  console.error('usage: new-article.mjs "<标题>" [--root <dir>] [--date YYYYMMDD]');
  process.exit(2);
}

// Must live inside the agent workspace: the Control UI file panel refuses to open
// anything outside the session root.
const root = flag("root", `${process.env.HOME}/.openclaw/workspace/wx-content`);
const now = new Date();
const date = flag("date", `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`);

// "/" and "|" would split the path, so they are the only characters sanitised.
const safe = title.replace(/[\/|]/g, "-").trim();
const dir = join(root, date, safe);
const md = join(dir, "content.md");

if (existsSync(md)) {
  console.error(`已存在，不覆盖: ${md}`);
  process.exit(1);
}
mkdirSync(join(dir, "resources"), { recursive: true });
writeFileSync(md, `# ${title}\n\n`, "utf8");

console.log(JSON.stringify({ date, title: safe, dir, contentMd: md, resources: join(dir, "resources") }, null, 2));
