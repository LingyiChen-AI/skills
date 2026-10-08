# github-image-upload

把本地图片传到 GitHub 仓库当图床，返回 jsDelivr CDN 链接。

## 配置

```bash
export GITHUB_TOKEN=<GitHub PAT，需 Contents 读写权限>
```

在 openclaw 里用时注意：`GITHUB_TOKEN` 会被刻意从 agent 环境中抹掉，
需要换一个变量名（例如 `WX_GITHUB_TOKEN`）并相应改脚本。

默认仓库 `LingyiChen-AI/images`，路径规则 `{project}/images/YYYY/MM/filename`，
`{project}` 取当前工作目录名。
