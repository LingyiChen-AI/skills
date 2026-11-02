// 生产只读查询：经飞书「研发SQL执行群」的「SQL执行窗口」执行（复用 sql-window skill 的校验、串行锁和幂等发送）。
// 不直连数据库、不读口令。
//
//   node sqlq.mjs --db voc_config --cost "走主键 id，1 行" "SELECT id, name FROM t WHERE id = 1"
//   node sqlq.mjs --list                 列出可用库
//   node sqlq.mjs --fetch <请求ID>        再读一次之前超时的请求，拿到结果后释放锁
//   node sqlq.mjs --test                 发 SELECT 1 验证整条链路（会在 SQL 群里发一条消息）
//
// 规则：只允许单条 SELECT；没写 LIMIT 自动补 50，上限 200；自动加 MAX_EXECUTION_TIME(5000)；
// 不许 SELECT *；看表结构改查 information_schema.columns / statistics。
import {existsSync, readFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {delimiter, dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const readJson = p => JSON.parse(readFileSync(p, 'utf8').replace(/^﻿/, ''));
const expand = p => p.replace(/^~(?=$|[\\/])/, homedir());
const sleep = ms => new Promise(r => setTimeout(r, ms));
const die = msg => { console.log(`[失败] ${msg}`); process.exit(1); };

const cfg = readJson(join(HERE, '..', 'config.json'));
const swDir = expand(cfg.sql_window?.skill_dir ?? '~/.claude/skills/sql-window');
const codexHome = process.env.CODEX_HOME ?? join(homedir(), '.codex');
const connPath = join(codexHome, 'sql-window', 'connection.json');
const ROOT = resolve(join(codexHome, 'sql-window', 'requests'));
const sw = await import(pathToFileURL(join(swDir, 'scripts', 'sql-window.mjs')).href);

// ---------- lark-cli：用户身份，绕开 .cmd 壳 ----------
const BRIDGE_ENV = ['LARK_CHANNEL', 'LARK_CHANNEL_HOME', 'LARK_CHANNEL_PROFILE', 'LARKSUITE_CLI_CONFIG_DIR'];
function findRunJs() {
  for (const d of (process.env.PATH ?? '').split(delimiter)) {
    if (d && (existsSync(join(d, 'lark-cli.cmd')) || existsSync(join(d, 'lark-cli')))) {
      const p = join(d, 'node_modules', '@larksuite', 'cli', 'scripts', 'run.js');
      if (existsSync(p)) return p;
    }
  }
  die('找不到 lark-cli（@larksuite/cli 的 run.js）');
}
const RUN_JS = findRunJs();
function run(args, cwd) {
  const env = {...process.env, LARKSUITE_CLI_NO_UPDATE_NOTIFIER: '1', LARKSUITE_CLI_NO_SKILLS_NOTIFIER: '1'};
  for (const k of BRIDGE_ENV) delete env[k];
  const r = spawnSync(process.execPath, [RUN_JS, ...args], {cwd, encoding: 'utf8', windowsHide: true, timeout: 45000, maxBuffer: 8 * 1024 * 1024, env});
  if (r.error) throw Error(`CLI interrupted (${r.error.code}); delivery may be unknown`);
  let env2;
  try { env2 = JSON.parse(r.stdout || r.stderr); } catch { throw Error(`Invalid CLI response (exit ${r.status}); delivery may be unknown`); }
  if (r.status !== 0 || env2.ok !== true) throw Error(JSON.stringify(env2.error ?? {message: 'CLI failed'}));
  return env2;
}

// ---------- 连接配置 ----------
if (!existsSync(connPath)) die(`缺少 ${connPath}：先按 sql-window skill 完成首次接通`);
const conn = readJson(connPath);
if (!/^oc_/.test(conn.chatId ?? '') || !/^ou_/.test(conn.botId ?? '')) die(`${connPath} 里 chatId / botId 不完整`);

// ---------- 读结果 ----------
const isBot = m => m?.sender && (m.sender.id === conn.botAppId || m.sender.open_bot_id === conn.botId);
const text = m => (typeof m.content === 'string' ? m.content : JSON.stringify(m.content)).replace(/\n\s*\n/g, '\n');

function readReply(id) {
  const state = readJson(join(ROOT, id, 'state.json'));
  if (!/^om_/.test(state.messageId ?? '')) return null;
  const {path} = sw.fetchResult(ROOT, id, false, run);
  const thread = (readJson(path).data?.messages ?? []).filter(m => isBot(m) && m.message_id !== state.messageId);
  const posts = thread.filter(m => m.msg_type !== 'file');
  if (posts.length) {
    const files = thread.filter(m => m.msg_type === 'file').map(m => m.message_id);
    return {ids: [...posts.map(m => m.message_id), ...files], body: posts.reverse().map(text).join('\n')};
  }
  // 拒绝执行时机器人会直接回复原消息（不在话题里）
  const recent = run(['im', '+chat-messages-list', '--as', 'user', '--chat-id', conn.chatId, '--page-size', '20', '--no-reactions', '--json'], join(ROOT, id));
  const direct = (recent.data?.messages ?? []).filter(m => isBot(m) && m.reply_to === state.messageId);
  if (direct.length) return {ids: direct.map(m => m.message_id), body: direct.reverse().map(text).join('\n')};
  return null;
}

async function waitReply(id, tries = 6) {
  for (let i = 0; i < tries; i++) {
    await sleep(i === 0 ? 4000 : 10000);
    const reply = readReply(id);
    if (reply) {
      sw.finish(ROOT, id, `机器人终态回复 ${reply.ids.join(',')}：${reply.body.slice(0, 60).replace(/\s+/g, ' ')}`);
      return reply;
    }
  }
  return null;
}

function stateOf(id) {
  const p = join(ROOT, id, 'state.json');
  return existsSync(p) ? readJson(p) : {status: 'prepared'};
}

// 别的请求占着锁：已发送的先尝试收尾，在途的等一会儿
async function acquire(selfId) {
  for (let i = 0; i < 9; i++) {
    const owner = join(ROOT, '.production-active', 'owner.json');
    if (!existsSync(owner)) return;
    const other = readJson(owner).id;
    if (other === selfId) return;
    const st = stateOf(other);
    if (st.status === 'sent') {
      const reply = readReply(other);
      if (reply) { sw.finish(ROOT, other, `机器人终态回复 ${reply.ids.join(',')}（后续请求收尾）`); continue; }
    } else if (st.status === 'unknown') {
      die(`上一个请求 ${other} 发送结果不明，需要人工到 SQL 群核对原消息后再 finish（见 sql-window skill「中断和异常」），不能自动清锁`);
    }
    await sleep(10000);
  }
  die('SQL 执行窗口一直被别的请求占用（约 90 秒），稍后再查');
}

// ---------- SQL 规整 ----------
function normalize(raw) {
  let sql = raw.trim().replace(/;\s*$/, '').trim();
  if (!/^select\b/i.test(sql)) die('只支持单条 SELECT。看表结构：SELECT column_name, column_type, column_key FROM information_schema.columns WHERE table_schema=\'库\' AND table_name=\'表\' LIMIT 100；看索引查 information_schema.statistics');
  if (!/^select\s*\/\*\+/i.test(sql)) sql = sql.replace(/^select/i, 'SELECT /*+ MAX_EXECUTION_TIME(5000) */');
  const hasFrom = /\bfrom\b/i.test(sql);
  const m = sql.match(/\blimit\s+(\d+)\s*$/i);
  let rows = 1;
  if (m) {
    rows = Number(m[1]);
    if (rows > 200) die(`LIMIT ${rows} 超过上限 200`);
  } else if (hasFrom) {
    sql += ' LIMIT 50';
    rows = 50;
  }
  return {sql, rows: Math.max(rows, 1)};
}

function arg(name) {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
}

function printReply(id, reply) {
  console.log(`[请求] ${id}`);
  console.log(reply.body.trim());
}

// ---------- main ----------
const dbs = Object.entries(cfg.dbs ?? {});
if (process.argv.includes('--list')) {
  for (const [k, d] of dbs) console.log(`${k}\t${d.kind}\t${d.database}`);
  process.exit(0);
}

const fetchId = arg('--fetch');
if (fetchId) {
  const st = stateOf(fetchId);
  if (st.status === 'finished') die(`请求 ${fetchId} 已经收尾：${st.evidence ?? ''}`);
  if (st.status !== 'sent') die(`请求 ${fetchId} 状态是 ${st.status}，不能读结果`);
  const reply = await waitReply(fetchId, 3);
  if (!reply) die(`请求 ${fetchId} 仍未返回结果（SQL 执行窗口没有回复），不要重发同一条查询`);
  printReply(fetchId, reply);
  process.exit(0);
}

let database, raw, cost, scope;
if (process.argv.includes('--test')) {
  database = dbs.find(([, d]) => d.kind === 'mysql')?.[1].database ?? die('没有登记 MySQL 库');
  raw = 'SELECT /*+ MAX_EXECUTION_TIME(5000) */ 1 AS codex_connection_test';
  cost = '没有 FROM 或业务表读取，返回一行常量';
  scope = '连接联调，仅常量表达式，不读业务表';
} else {
  const alias = arg('--db') ?? die('缺少 --db <库>（node sqlq.mjs --list 查看）');
  const d = cfg.dbs?.[alias] ?? die(`库 ${alias} 未登记（node sqlq.mjs --list 查看）`);
  if (d.kind !== 'mysql') die(`${alias} 是 ${d.kind}，SQL 执行窗口只支持 MySQL`);
  database = d.database;
  cost = arg('--cost') ?? die('缺少 --cost "<扫描成本依据：走哪个主键/索引/条件，预计多少行>"');
  scope = arg('--scope') ?? 'bug 排查只读复现';
  const flags = new Set(['--db', '--cost', '--scope']);
  raw = process.argv.slice(2).filter((x, i, a) => !flags.has(x) && !flags.has(a[i - 1])).join(' ');
  if (!raw.trim()) die('缺少 SQL');
}

const {sql, rows} = normalize(raw);
let req;
try {
  req = sw.prepare(ROOT, {database, chatId: conn.chatId, botId: conn.botId, sql,
    review: {environment: 'prod', scope, costEvidence: cost, expectedRows: rows, serverTimeoutMs: 5000}});
} catch (e) {
  die(`SQL 未通过检查：${e.message}`);
}
await acquire(req.id);
let sent;
try {
  sent = sw.submit(ROOT, req.id, run);
} catch (e) {
  die(`发送失败（请求 ${req.id}，状态 ${stateOf(req.id).status}）：${e.message}`);
}
const reply = await waitReply(req.id);
if (!reply) {
  console.log(`[未完成] 请求 ${req.id} 已发到 SQL 群（${sent.messageId}），约 1 分钟内没有结果。`);
  console.log(`稍后执行 node ${join(HERE, 'sqlq.mjs').replace(/\\/g, '/')} --fetch ${req.id} 再读一次；不要重发同一条查询。`);
  process.exit(2);
}
printReply(req.id, reply);
