#!/usr/bin/env node
// Markdown -> WeChat-ready inline-styled HTML.
// Port of raphael-publish (github.com/liuxiaopai-ai/raphael-publish) applyTheme +
// makeWeChatCompatible, running headless on linkedom instead of the browser DOM.
//
// Usage:
//   node render.mjs <input.md> [--theme <id>] [--out <file.html>] [--title <t>] [--json]
//   node render.mjs --list-themes
import { readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import hljs from "highlight.js";
import { parseHTML } from "linkedom";
import MarkdownIt from "markdown-it";

const HERE = dirname(fileURLToPath(import.meta.url));
const THEMES = JSON.parse(readFileSync(join(HERE, "themes.json"), "utf8"));

const argv = process.argv.slice(2);
const flag = (name, fallback = null) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : fallback;
};
const has = (name) => argv.includes(`--${name}`);

if (has("list-themes")) {
  const groups = { classic: "经典", modern: "潮流", extra: "更多风格" };
  for (const g of Object.keys(groups)) {
    console.log(`\n${groups[g]}`);
    for (const t of THEMES.filter((x) => x.group === g)) {
      console.log(`  ${t.id.padEnd(12)} ${t.name.padEnd(14)} ${t.description}`);
    }
  }
  process.exit(0);
}

const input = argv.find((a) => !a.startsWith("--") && argv[argv.indexOf(a) - 1] !== "--theme" &&
  argv[argv.indexOf(a) - 1] !== "--out" && argv[argv.indexOf(a) - 1] !== "--title");
if (!input) {
  console.error("usage: render.mjs <input.md> [--theme <id>] [--out <file.html>] [--title <t>] [--json]");
  console.error("       render.mjs --list-themes");
  process.exit(2);
}

const themeId = flag("theme", "apple");
const theme = THEMES.find((t) => t.id === themeId);
if (!theme) {
  console.error(`unknown theme "${themeId}" — run --list-themes`);
  process.exit(2);
}
const style = theme.styles;

// --- markdown -> html --------------------------------------------------------
const CODE_DOTS =
  '<div style="margin-bottom: 12px; white-space: nowrap;">' +
  ['#ff5f56', '#ffbd2e', '#27c93f']
    .map((c, i) => `<span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: ${c};${i < 2 ? " margin-right: 6px;" : ""}"></span>`)
    .join("") +
  "</div>";

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: false,
  highlight(str, lang) {
    let code;
    if (lang && hljs.getLanguage(lang)) {
      try {
        code = hljs.highlight(str, { language: lang }).value;
      } catch {
        code = md.utils.escapeHtml(str);
      }
    } else {
      code = md.utils.escapeHtml(str);
    }
    return `<pre>${CODE_DOTS}<code class="hljs">${code}</code></pre>`;
  },
});

const source = readFileSync(input, "utf8");
const rawHtml = md.render(source);

// linkedom only builds a real document from a full <html> wrapper; a bare
// fragment parses to an empty body.
const { document } = parseHTML(`<html><head></head><body>${rawHtml}</body></html>`);

// --- applyTheme: inline every style the theme declares -----------------------
// Headings must not inherit the body treatment of strong/em/a/code.
const HEADING_OVERRIDES = {
  strong: "font-weight: 700; color: inherit !important; background-color: transparent !important;",
  em: "font-style: italic; color: inherit !important; background-color: transparent !important;",
  a: "color: inherit !important; text-decoration: none !important; border-bottom: 1px solid currentColor !important; background-color: transparent !important;",
  code: "color: inherit !important; background-color: transparent !important; border: none !important; padding: 0 !important;",
};

for (const tag of Object.keys(style)) {
  if (tag === "container") continue;
  for (const el of document.querySelectorAll(tag)) {
    const inHeading = el.closest("h1, h2, h3, h4, h5, h6");
    const css = inHeading && HEADING_OVERRIDES[tag] ? HEADING_OVERRIDES[tag] : style[tag];
    el.setAttribute("style", css);
  }
}

// --- makeWeChatCompatible ----------------------------------------------------
const containerStyle = style.container || "";
const section = document.createElement("section");
section.setAttribute("style", containerStyle);
for (const node of [...document.body.childNodes]) section.appendChild(node);

// WeChat mangles <p> nested inside <li>; downgrade them to <span>.
for (const li of section.querySelectorAll("li")) {
  const hasBlock = [...li.children].some((c) => ["P", "DIV", "UL", "OL", "BLOCKQUOTE"].includes(c.tagName));
  if (!hasBlock) continue;
  for (const p of [...li.querySelectorAll("p")]) {
    const span = document.createElement("span");
    span.innerHTML = p.innerHTML;
    const s = p.getAttribute("style");
    if (s) span.setAttribute("style", s);
    p.parentNode.replaceChild(span, p);
  }
}

// WeChat's editor drops inherited font properties, so push them onto each block.
const pick = (prop) => containerStyle.match(new RegExp(`${prop}:\\s*([^;]+);`))?.[1];
const font = pick("font-family");
const size = pick("font-size");
const color = pick("color");
const lineHeight = pick("line-height");

for (const node of section.querySelectorAll("p, li, h1, h2, h3, h4, h5, h6, blockquote, span")) {
  if (node.tagName === "SPAN" && node.closest("pre, code")) continue;
  let css = node.getAttribute("style") || "";
  if (font && !css.includes("font-family:")) css += ` font-family: ${font};`;
  if (lineHeight && !css.includes("line-height:")) css += ` line-height: ${lineHeight};`;
  if (size && !css.includes("font-size:") && ["P", "LI", "BLOCKQUOTE", "SPAN"].includes(node.tagName)) {
    css += ` font-size: ${size};`;
  }
  if (color && !css.includes("color:")) css += ` color: ${color};`;
  node.setAttribute("style", css.trim());
}

// Pull a trailing CJK punctuation mark inside the emphasis so WeChat cannot
// break the line between them.
const TEXT_NODE = 3;
for (const node of section.querySelectorAll("strong, b, em, span, a, code")) {
  const next = node.nextSibling;
  if (!next || next.nodeType !== TEXT_NODE) continue;
  const m = (next.textContent || "").match(/^\s*([：；，。！？、:])([\s\S]*)$/);
  if (!m) continue;
  node.appendChild(document.createTextNode(m[1]));
  if (m[2]) next.textContent = m[2];
  else next.parentNode.removeChild(next);
}

let html = section.outerHTML;
// Word-joiner keeps the punctuation glued to the preceding inline tag.
html = html.replace(/(<\/(?:strong|b|em|span|a|code)>)\s*([：；，。！？、])/g, "$1⁠$2");

// WeChat caps draft content at 20000 characters and inline styles are ~80% of the
// payload, so compaction is applied in tiers — least invasive first. Each tier is a
// pure string pass over the rendered HTML.
const SHORT_STACK = "-apple-system, sans-serif";
const TIERS = [
  {
    name: "short-font-stack",
    note: "字体栈缩短 + 去多余空格（移动端渲染不变）",
    apply: (h) =>
      h
        // The stack contains &quot; entities whose trailing ";" breaks a naive
        // "up to the next semicolon" match — anchor on the sans-serif terminator.
        .replace(/font-family:\s*-apple-system[\s\S]*?sans-serif/g, `font-family: ${SHORT_STACK}`)
        .replace(/font-family:\s*&quot;?SF Mono[\s\S]*?monospace/g, "font-family: monospace")
        .replace(/;\s*"/g, '"')
        .replace(/;\s+/g, ";"),
  },
  {
    name: "drop-important",
    note: "去掉 !important（微信样式表若有 important 规则可能反压过来）",
    apply: (h) => h.replace(/\s*!important/g, ""),
  },
  {
    name: "drop-inherited-dupes",
    note: "去掉与容器重复的 font-family/font-size/line-height（靠继承）",
    apply: (h) => {
      const container = /<section style="([^"]*)"/.exec(h)?.[1] ?? "";
      const get = (prop) => new RegExp(`${prop}:\\s*([^;"]+)`).exec(container)?.[1]?.trim();
      let out = h;
      for (const prop of ["font-family", "font-size", "line-height"]) {
        const v = get(prop);
        if (!v) continue;
        // Only strip from descendants; the opening <section> keeps the declaration.
        const re = new RegExp(`\\s*${prop}:\\s*${v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")};?`, "g");
        const head = out.slice(0, out.indexOf(">") + 1);
        out = head + out.slice(head.length).replace(re, "");
      }
      return out;
    },
  },
];

const maxChars = Number(flag("max-chars", has("fit") ? 20000 : 0));
const applied = [];
if (has("compact") || maxChars > 0) {
  // --compact alone = tier 1 only (historical behaviour); --drop-important adds tier 2.
  const explicit = has("compact") && !maxChars;
  for (const tier of TIERS) {
    if (explicit) {
      if (tier.name === "drop-important" && !has("drop-important")) continue;
      if (tier.name === "drop-inherited-dupes") continue;
    } else if (maxChars > 0 && html.length <= maxChars) {
      break;
    }
    html = tier.apply(html);
    applied.push(tier.name);
  }
}

const title = flag("title") || (source.match(/^#\s+(.+)$/m)?.[1] ?? basename(input, ".md"));
const out = flag("out");
if (out) writeFileSync(out, html, "utf8");

const stats = {
  input,
  theme: `${theme.id} (${theme.name})`,
  title,
  sourceBytes: Buffer.byteLength(source, "utf8"),
  htmlBytes: Buffer.byteLength(html, "utf8"),
  images: section.querySelectorAll("img").length,
  headings: section.querySelectorAll("h1,h2,h3,h4").length,
  codeBlocks: section.querySelectorAll("pre").length,
  tables: section.querySelectorAll("table").length,
  inlineStyled: section.querySelectorAll("[style]").length,
  htmlChars: html.length,
  compact: has("compact"),
  compaction: applied,
  maxChars: maxChars || null,
  fits: maxChars ? html.length <= maxChars : null,
  // When even full compaction is not enough, say how much prose has to go.
  trimChineseCharsBy: maxChars && html.length > maxChars
    ? Math.ceil(((html.length - maxChars) / html.length) * (source.match(/[一-龥]/g) ?? []).length)
    : 0,
  out: out ?? "(stdout)",
};

if (has("json")) console.log(JSON.stringify(stats, null, 2));
else if (out) {
  console.log(
    `typeset ${stats.title}\n  theme  ${stats.theme}\n  html   ${stats.htmlBytes} bytes -> ${out}\n` +
      `  nodes  ${stats.headings} 标题 / ${stats.images} 图 / ${stats.tables} 表 / ${stats.codeBlocks} 代码块 / ${stats.inlineStyled} 个内联样式节点`,
  );
} else console.log(html);
