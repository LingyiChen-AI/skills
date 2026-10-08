#!/usr/bin/env node
// Keyless web search fallback: openclaw's web_search needs a provider API key,
// so when none is configured this scrapes Bing's result page instead.
// Results feed research only — always open the real pages before citing them.
//
// Usage: node search.mjs "<query>" [--count 8] [--market zh-CN] [--json]
const argv = process.argv.slice(2);
const flag = (n, d) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : d;
};
const query = argv.find((a) => !a.startsWith("--") && argv[argv.indexOf(a) - 1] !== "--count" && argv[argv.indexOf(a) - 1] !== "--market");
if (!query) {
  console.error('usage: search.mjs "<query>" [--count 8] [--market zh-CN] [--json]');
  process.exit(2);
}
const count = Number(flag("count", 8));
const market = flag("market", "zh-CN");

const url = `https://www.bing.com/search?q=${encodeURIComponent(query)}&count=20&mkt=${encodeURIComponent(market)}`;
const res = await fetch(url, {
  headers: {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": `${market},zh;q=0.9,en;q=0.8`,
  },
});
if (!res.ok) {
  console.error(`search failed: HTTP ${res.status}`);
  process.exit(1);
}
const html = await res.text();

const ENTITIES = { amp: "&", quot: '"', lt: "<", gt: ">", nbsp: " ", ensp: " ", emsp: " ", "#39": "'", apos: "'" };
const strip = (s) =>
  s.replace(/<[^>]+>/g, "")
    // Bing peppers snippets with &ensp;/&#0183; so decode numeric refs too.
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCharCode(parseInt(n, 16)))
    .replace(/&([a-z#0-9]+);/gi, (m, name) => ENTITIES[name.toLowerCase()] ?? m)
    .replace(/\s+/g, " ")
    .trim();

const results = [];
const seen = new Set();
// Each organic hit is an <li class="b_algo"> block: title in h2>a, blurb in b_caption.
for (const block of html.split('<li class="b_algo"').slice(1)) {
  const t = /<h2[^>]*>\s*<a[^>]+href="(https?:[^"]+)"[^>]*>([\s\S]*?)<\/a>/.exec(block);
  if (!t) continue;
  const link = t[1].replace(/&amp;/g, "&");
  // Bing wraps outbound links in a /ck/a redirector; keep the display host instead.
  const cite = /<cite[^>]*>([\s\S]*?)<\/cite>/.exec(block);
  const title = strip(t[2]);
  if (!title || seen.has(title)) continue;
  seen.add(title);
  const cap = /class="b_caption"[\s\S]*?<p[^>]*>([\s\S]*?)<\/p>/.exec(block);
  results.push({
    title,
    source: cite ? strip(cite[1]).split("›")[0].trim() : "",
    snippet: cap ? strip(cap[1]).slice(0, 220) : "",
    url: /\/ck\/a\?/.test(link) ? (cite ? "https://" + strip(cite[1]).split("›")[0].trim().replace(/^https?:\/\//, "") : link) : link,
  });
  if (results.length >= count) break;
}

if (argv.includes("--json")) {
  console.log(JSON.stringify({ query, count: results.length, results }, null, 2));
} else {
  console.log(`query: ${query}\nhits : ${results.length}\n`);
  for (const [i, r] of results.entries()) {
    console.log(`${i + 1}. ${r.title}`);
    if (r.source) console.log(`   ${r.source}`);
    if (r.snippet) console.log(`   ${r.snippet}`);
    console.log(`   ${r.url}\n`);
  }
}
