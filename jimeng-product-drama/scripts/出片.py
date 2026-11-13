"""按 <项目>/分镜.json 提交即梦 multimodal2video（全能参考），并发轮询，下载到 <项目>/视频段/段XX.mp4。

用法：
  python 出片.py <项目目录> 1            # 先出第 1 段验证
  python 出片.py <项目目录> all          # 出全部（已有 段XX.mp4 的跳过）
  python 出片.py <项目目录> 1 3 --redo   # 删掉旧文件重出
  python 出片.py <项目目录> all --dry-run  # 只看要提交什么、预估积分
提交记录写 <项目>/出片记录.json；中途中断后再跑同样命令会接着轮询，不会重复提交。
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import sys as _sys; from pathlib import Path as _P; _sys.path.insert(0, str(_P(__file__).resolve().parent))  # 兼容 python -I
from common import dreamina

p = argparse.ArgumentParser()
p.add_argument("project")
p.add_argument("ids", nargs="+", help="段号，或 all")
p.add_argument("--dry-run", action="store_true")
p.add_argument("--redo", action="store_true", help="删除已有视频和提交记录后重出")
p.add_argument("--timeout-h", type=float, default=3)
a = p.parse_args()

root = Path(a.project).resolve()
cfg = json.loads((root / "分镜.json").read_text(encoding="utf-8"))
out = root / "视频段"
out.mkdir(exist_ok=True)
state_f = root / "出片记录.json"
state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
save = lambda: state_f.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

segs = cfg["segments"] if a.ids == ["all"] else [s for s in cfg["segments"] if str(s["id"]) in a.ids]


def seg_refs(s):
    """段里写了 refs 就用段自己的（每段出场角色不同），否则用全局 refs。顺序即 @图片1..N。"""
    paths = [str((root / r).resolve()) for r in s.get("refs", cfg.get("refs", []))]
    for r in paths:
        if not Path(r).exists():
            raise SystemExit(f"段{s['id']:02d} 参考图不存在：{r}")
    if len(paths) > 9:
        raise SystemExit(f"段{s['id']:02d} 参考图 {len(paths)} 张，超过 9 张上限")
    return paths


for s in segs:
    seg_refs(s)  # 提交前先把所有段的参考图检查一遍，缺图直接停
rate = cfg.get("credit_per_second", 6)

pending = {}
todo_seconds = 0
for s in segs:
    key = f"段{s['id']:02d}"
    target = out / f"{key}.mp4"
    if a.redo and not a.dry_run:
        target.unlink(missing_ok=True)
        state.pop(key, None)
    if target.exists() and not (a.redo and a.dry_run):
        print(f"{key} 已存在，跳过（重出加 --redo）")
        continue
    todo_seconds += s["duration"]
    prompt = s["prompt"].rstrip() + "\n" + cfg.get("style", "")
    if len(prompt) > 1500:
        raise SystemExit(f"{key} prompt {len(prompt)} 字，超过 1500 字上限")
    cmd = ["multimodal2video"]
    for r in seg_refs(s):
        cmd += ["--image", r]
    cmd += ["--prompt", prompt, "--duration", str(s["duration"]), "--ratio", cfg.get("ratio", "9:16"),
            "--video_resolution", cfg.get("video_resolution", "720p"),
            "--model_version", cfg.get("model_version", "seedance2.0fast_vip"), "--poll", "0"]
    if a.dry_run:
        print(f"{key} {s['duration']}s，prompt {len(prompt)} 字，预估 {s['duration'] * rate} 积分")
        continue
    prev = state.get(key, {})
    # 记录是 success 但文件被删了 = 用户想重出，重新提交
    if prev.get("submit_id") and prev.get("status") not in ("fail", "submit_error", "success"):
        print(f"{key} 已提交过 {prev['submit_id']}，继续轮询")
        pending[key] = prev["submit_id"]
        continue
    data, raw = dreamina(cmd)
    if not data or "submit_id" not in data:
        print(f"{key} 提交失败：{raw[:500]}")
        state[key] = {"status": "submit_error", "error": raw[:500]}
        save()
        continue
    state[key] = {"submit_id": data["submit_id"], "status": data.get("gen_status"),
                  "credit": data.get("credit_count"), "eta_s": data.get("estimated_remaining_seconds"),
                  "queue_idx": (data.get("queue_info") or {}).get("queue_idx")}
    save()
    print(f"{key} 已提交 {data['submit_id']}，扣 {data.get('credit_count')} 积分，"
          f"预计 {data.get('estimated_remaining_seconds')} 秒", flush=True)
    pending[key] = data["submit_id"]

if a.dry_run:
    print(f"待出 {todo_seconds} 秒，合计预估 {todo_seconds * rate} 积分（按 {rate} 积分/秒）")
    raise SystemExit(0)

deadline = time.time() + a.timeout_h * 3600
while pending and time.time() < deadline:
    time.sleep(20)
    for key, sid in list(pending.items()):
        tmp = out / f"_tmp_{key}"
        tmp.mkdir(exist_ok=True)
        data, raw = dreamina(["query_result", "--submit_id", sid, "--download_dir", str(tmp)])
        st = (data or {}).get("gen_status")
        if st == "success":
            vids = list(tmp.glob("*.mp4"))
            if not vids:
                continue  # 状态成功但还没下完，下一轮再查
            shutil.move(str(vids[0]), out / f"{key}.mp4")
            shutil.rmtree(tmp, ignore_errors=True)
            state[key]["status"] = "success"
            save()
            print(f"{key} 完成 → 视频段/{key}.mp4", flush=True)
            del pending[key]
        elif st == "fail":
            shutil.rmtree(tmp, ignore_errors=True)
            state[key].update(status="fail", fail_reason=data.get("fail_reason"))
            save()
            print(f"{key} 失败：{data.get('fail_reason')}", flush=True)
            del pending[key]
for key, sid in pending.items():
    print(f"{key} 超时未完成，submit_id={sid}；再跑同样命令会继续轮询")
