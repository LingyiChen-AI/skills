"""把项目最新的 release 分支同步到 <code_root>/<项目>（只读分析用，Git Bash 下即 /tmp/auto-bug-tester/<项目>）。

每次都 fetch 并强制切到最新分支，丢弃该目录里的任何本地改动。项目在 config.json 的 projects 里登记。

  python sync_code.py my-service
  python sync_code.py my-service --branch release/V3.2
"""
import argparse
import fnmatch
import re
import subprocess

from _common import expand, load_config


def git(args, cwd, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：\n{p.stderr.strip()}")
    return p.stdout.strip()


def version_key(branch):
    """release/V3.3 → (3,3,0,0)；release/V3.0-20260824 → (3,0,0,20260824)。不像版本号的排最前。"""
    name = branch.rsplit("/", 1)[-1]
    m = re.match(r"[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-_](\d{8}))?", name)
    if not m:
        return (-1, -1, -1, -1)
    return tuple(int(x) if x else 0 for x in m.groups())


def latest_branch(repo_dir, glob):
    refs = git(["for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin/"], cwd=repo_dir).split()
    refs = [r for r in refs if fnmatch.fnmatch(r, glob)]
    if not refs:
        raise SystemExit(f"远端没有匹配 {glob} 的分支")
    return max(refs, key=version_key)


def sync(project, branch=None):
    cfg = load_config()
    if project not in cfg["projects"]:
        raise SystemExit(f"未登记的项目 {project}，可用：{sorted(cfg['projects'])}")
    p = cfg["projects"][project]
    root = expand(cfg["code_root"])
    root.mkdir(parents=True, exist_ok=True)
    repo_dir = root / project
    if not (repo_dir / ".git").exists():
        print(f"首次克隆 {p['repo']} → {repo_dir}")
        git(["clone", "--no-checkout", p["repo"], str(repo_dir)], cwd=root)
    git(["fetch", "origin", "--prune", "--quiet"], cwd=repo_dir)
    branch = branch or latest_branch(repo_dir, p.get("branch_glob", "release/*"))
    git(["checkout", "--force", "--detach", f"origin/{branch}"], cwd=repo_dir)
    git(["clean", "-fdq"], cwd=repo_dir)
    info = git(["log", "-1", "--format=%h %ci %an %s"], cwd=repo_dir)
    return repo_dir, branch, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--branch", help="指定分支，默认按 branch_glob 取版本号最大的")
    a = ap.parse_args()
    repo_dir, branch, info = sync(a.project, a.branch)
    rules = load_config()["projects"][a.project].get("rules_file")
    print(f"项目: {a.project}")
    print(f"目录: {repo_dir}  (Git Bash: /tmp/auto-bug-tester/{a.project})")
    print(f"分支: {branch}")
    print(f"提交: {info}")
    if rules:
        print(f"先读: {repo_dir / rules}")


if __name__ == "__main__":
    main()
