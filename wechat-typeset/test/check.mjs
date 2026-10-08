// Assert the rendered HTML satisfies what WeChat's editor needs.
import { readFileSync } from "node:fs";
import { parseHTML } from "linkedom";
const html = readFileSync(process.argv[2], "utf8");
const { document } = parseHTML(`<html><head></head><body>${html}</body></html>`);
const root = document.body.firstElementChild;
const checks = [];
const ok = (name, cond, detail = "") => checks.push([cond, name, detail]);

ok("根节点是 <section>", root?.tagName === "SECTION", root?.tagName);
ok("根节点带容器样式", (root?.getAttribute("style") || "").includes("font-family"));
const unstyled = [...document.querySelectorAll("p,h1,h2,h3,h4,li,blockquote,td,th,img,a,pre,table,hr")]
  .filter((e) => !e.getAttribute("style"));
ok("所有块级元素都有内联样式", unstyled.length === 0, unstyled.map((e) => e.tagName).join(","));
ok("没有 <style> 标签", document.querySelectorAll("style").length === 0);
ok("没有 class 残留（除 hljs）", [...document.querySelectorAll("[class]")].every((e) => /hljs/.test(e.className)));
ok("li 内没有 <p>", document.querySelectorAll("li p").length === 0);
const p = document.querySelector("p");
const rootStyle = root?.getAttribute("style") || "";
// Tier 3 of --fit strips declarations that merely duplicate the container, so a
// property counts as present if it is on the paragraph OR inherited from <section>.
const resolved = (prop) => (p?.getAttribute("style") || "").includes(prop) || rootStyle.includes(prop);
ok("段落字号可解析（自带或继承）", resolved("font-size"));
ok("段落行高可解析（自带或继承）", resolved("line-height"));
const h2 = document.querySelector("h2 strong");
ok("标题内 strong 用 inherit 颜色", !h2 || (h2.getAttribute("style") || "").includes("inherit"), h2?.getAttribute("style"));
// The DOM pass pulls trailing CJK punctuation inside the emphasis; the
// word-joiner is only a fallback. What matters is that no split pair remains.
const splitPairs = html.match(/<\/(?:strong|b|em|span|a|code)>[：；，。！？、]/g) || [];
ok("标点未与强调标签分离", splitPairs.length === 0, splitPairs.slice(0, 3).join(" "));
ok("标点已吸入强调标签", /[：；，。！？、]<\/(?:strong|em|b|code|a)>/.test(html));
// Only assert on elements this document actually contains.
if (document.querySelector("pre")) ok("代码块有 Mac 三点装饰", /border-radius: ?50%/.test(html));
if (document.querySelector("td")) ok("表格有边框样式", (document.querySelector("td").getAttribute("style") || "").includes("border"));
if (document.querySelector("img")) ok("图片 max-width 限制", (document.querySelector("img").getAttribute("style") || "").includes("max-width"));

let bad = 0;
for (const [pass, name, detail] of checks) {
  if (!pass) bad++;
  console.log(`${pass ? "  ok  " : "FAIL  "}${name}${pass || !detail ? "" : "   <- " + detail}`);
}
console.log(`\n${bad === 0 ? "PASS" : `FAIL ${bad} 项`}`);
process.exit(bad ? 1 : 0);
