#!/usr/bin/env node
// Push a typeset article into the WeChat Official Account draft box.
// Dry-run by default: nothing leaves the machine unless --commit is passed.
//
// Usage:
//   export WECHAT_APPID=... WECHAT_APPSECRET=...
//   node publish.mjs <article.html> --title "..." [--author ...] [--digest ...]
//                    [--thumb-media-id ...] [--commit]
import { readFileSync } from "node:fs";

const argv = process.argv.slice(2);
const flag = (name, fallback = null) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : fallback;
};
const commit = argv.includes("--commit");
const input = argv.find((a) => !a.startsWith("--") && !argv.slice(0, argv.indexOf(a)).some((x) =>
  ["--title", "--author", "--digest", "--thumb-media-id"].includes(x) && argv.indexOf(x) === argv.indexOf(a) - 1));

if (!input) {
  console.error('usage: publish.mjs <article.html> --title "..." [--commit]');
  process.exit(2);
}

const appId = process.env.WECHAT_APPID;
// Read the secret from the environment only — a CLI argument would persist in shell history.
const appSecret = process.env.WECHAT_APPSECRET;
if (!appId) {
  console.error("WECHAT_APPID not set");
  process.exit(2);
}

const html = readFileSync(input, "utf8");
const title = flag("title") || "(untitled)";
// draft/add rejects an article with no cover (40007 invalid media_id), and it will
// not accept an external URL — the image has to become a permanent material first.
const thumbFromUrl = flag("thumb-from-url") ||
  (argv.includes("--thumb-from-first-image")
    ? (html.match(/<img[^>]+src="(https?:\/\/[^"]+)"/)?.[1] ?? null)
    : null);
const article = {
  title,
  author: flag("author", ""),
  digest: flag("digest", ""),
  content: html,
  content_source_url: flag("source-url", ""),
  thumb_media_id: flag("thumb-media-id", ""),
  need_open_comment: 1,
  only_fans_can_comment: 0,
};

const bytes = Buffer.byteLength(html, "utf8");
console.log(`article   ${title}`);
console.log(`appid     ${appId}`);
console.log(`secret    ${appSecret ? `set (${appSecret.length} chars)` : "NOT SET"}`);
console.log(`content   ${html.length} 字符 / ${bytes} 字节（上限 20000 字符）`);
if (html.length > 20000) console.log(`warning   正文 ${html.length} 字符，超过微信 20000 上限，会被拒`);
const externalImgs = [...new Set([...html.matchAll(/<img[^>]+src="(https?:\/\/[^"]+)"/g)]
  .map((m) => m[1]).filter((u) => !/mmbiz\.qpic\.cn|mp\.weixin\.qq\.com/.test(u)))];
if (externalImgs.length) console.log(`body      ${externalImgs.length} 张外部图片将转存为微信图片（外链会被过滤）`);
if (thumbFromUrl) console.log(`thumb     将从 ${thumbFromUrl.slice(0, 72)} 上传为永久素材`);
else if (!article.thumb_media_id) console.log("warning   缺 thumb_media_id，draft/add 会返回 40007");

if (!commit) {
  console.log("\ndry-run —— 未发起任何请求。确认无误后加 --commit 真正提交。");
  console.log("将要调用：");
  console.log("  GET  https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=…&secret=…");
  if (externalImgs.length) console.log(`  POST https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=…  ×${externalImgs.length}`);
  if (thumbFromUrl) console.log("  POST https://api.weixin.qq.com/cgi-bin/material/add_material?type=image&access_token=…");
  console.log("  POST https://api.weixin.qq.com/cgi-bin/draft/add?access_token=…");
  process.exit(0);
}

if (!appSecret) {
  console.error("WECHAT_APPSECRET not set — cannot commit");
  process.exit(2);
}

const tokenUrl =
  `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential` +
  `&appid=${encodeURIComponent(appId)}&secret=${encodeURIComponent(appSecret)}`;
const tokenRes = await fetch(tokenUrl).then((r) => r.json());
if (!tokenRes.access_token) {
  console.error(`token failed: ${JSON.stringify(tokenRes)}`);
  process.exit(1);
}

console.log("access_token obtained");

// Upload the cover as a permanent material and use the returned media_id.
if (thumbFromUrl && !article.thumb_media_id) {
  console.log(`downloading ${thumbFromUrl}`);
  const imgRes = await fetch(thumbFromUrl);
  if (!imgRes.ok) {
    console.error(`cover download failed: HTTP ${imgRes.status}`);
    process.exit(1);
  }
  const buf = Buffer.from(await imgRes.arrayBuffer());
  const name = thumbFromUrl.split("/").pop()?.split("?")[0] || "cover.png";
  console.log(`downloaded ${name} (${buf.length} bytes)`);

  const form = new FormData();
  form.append("media", new Blob([buf]), name);
  const matRes = await fetch(
    `https://api.weixin.qq.com/cgi-bin/material/add_material?type=image&access_token=${tokenRes.access_token}`,
    { method: "POST", body: form },
  ).then((r) => r.json());
  if (!matRes.media_id) {
    console.error(`add_material failed: ${JSON.stringify(matRes)}`);
    process.exit(1);
  }
  article.thumb_media_id = matRes.media_id;
  console.log(`media_id=${matRes.media_id}`);
}

// "涉及图片url必须来源'上传图文消息内的图片获取URL'接口获取。外部图片url将被过滤。"
// So every external <img> in the body has to be re-hosted before the draft is created.
const bodyImages = [...new Set([...article.content.matchAll(/<img[^>]+src="(https?:\/\/[^"]+)"/g)]
  .map((m) => m[1])
  .filter((u) => !/mmbiz\.qpic\.cn|mp\.weixin\.qq\.com/.test(u)))];

if (bodyImages.length) {
  console.log(`body      ${bodyImages.length} 张外部图片需要转存（否则会被微信过滤）`);
  for (const src of bodyImages) {
    const imgRes = await fetch(src);
    if (!imgRes.ok) {
      console.error(`  body image failed: HTTP ${imgRes.status} ${src}`);
      process.exit(1);
    }
    const buf = Buffer.from(await imgRes.arrayBuffer());
    const name = src.split("/").pop()?.split("?")[0] || "img.png";
    const form = new FormData();
    form.append("media", new Blob([buf]), name);
    const up = await fetch(
      `https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=${tokenRes.access_token}`,
      { method: "POST", body: form },
    ).then((r) => r.json());
    if (!up.url) {
      console.error(`  uploadimg failed: ${JSON.stringify(up)}`);
      process.exit(1);
    }
    article.content = article.content.split(src).join(up.url);
    console.log(`  ${name} -> ${up.url}`);
  }
}

const draftRes = await fetch(
  `https://api.weixin.qq.com/cgi-bin/draft/add?access_token=${tokenRes.access_token}`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // WeChat rejects escaped non-ASCII, so post raw UTF-8 bytes.
    body: Buffer.from(JSON.stringify({ articles: [article] }), "utf8"),
  },
).then((r) => r.json());

if (draftRes.media_id) {
  console.log(`\ndraft created: media_id=${draftRes.media_id}`);
  console.log("草稿已进后台草稿箱，仍需人工确认后才会群发。");
} else {
  console.error(`draft/add failed: ${JSON.stringify(draftRes)}`);
  process.exit(1);
}
