---
name: github-image-upload
description: Upload images to GitHub repository via API and return jsDelivr CDN URL. Use this skill whenever the user wants to upload an image, screenshot, or picture, or needs a hosted image URL. Triggers on phrases like "upload image", "上传图片", "图片上传", "host this image", "传图片", "图床", or when the user provides an image file and wants it stored/shared online.
---

# GitHub Image Upload

Upload images to the GitHub repository `LingyiChen-AI/images` via GitHub Contents API, organized by project and date, and return a jsDelivr CDN URL (no CORS issues, fast globally).

## Configuration

- **Repository**: `LingyiChen-AI/images`
- **Token**: Read from environment variable `GITHUB_TOKEN`
- **Image path pattern**: `{project}/images/YYYY/MM/filename` (based on current date)
  - `{project}` is the current project directory name (e.g., `k8s-admin`)
- **CDN URL pattern**: `https://cdn.jsdelivr.net/gh/LingyiChen-AI/images/{project}/images/YYYY/MM/filename`

## Workflow

1. **Validate the token exists** — check that `GITHUB_TOKEN` is set in the environment. If not, tell the user to set it: `export GITHUB_TOKEN=your_token`

2. **Identify the image file(s)** — the user will provide file path(s). Verify each file exists and is a valid image (png, jpg, jpeg, gif, webp, svg, ico, bmp).

3. **Determine project name** — use the current working directory's folder name as the project prefix. For example, if working in `~/codes/myself/k8s-admin`, the project name is `k8s-admin`.

4. **Upload via GitHub API** — for each image, write the JSON payload to a temp file to avoid shell argument length limits, then upload:

```bash
DATE_PATH=$(date +"%Y/%m")
PROJECT="$(basename "$PWD")"
FILENAME=$(basename "$IMAGE_PATH")
REMOTE_PATH="${PROJECT}/images/${DATE_PATH}/${FILENAME}"

# Write JSON payload to temp file
TMPFILE=$(mktemp)
python3 -c "
import json, base64
with open('${IMAGE_PATH}', 'rb') as f:
    content = base64.b64encode(f.read()).decode()
payload = {'message': 'upload: ${FILENAME}', 'content': content}
with open('${TMPFILE}', 'w') as out:
    json.dump(payload, out)
"

# Upload via API
curl -s -w "\n%{http_code}" -X PUT \
  "https://api.github.com/repos/LingyiChen-AI/images/contents/${REMOTE_PATH}" \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"$TMPFILE"

rm -f "$TMPFILE"
```

5. **Handle the response**:
   - On success (HTTP 201), construct the jsDelivr CDN URL and present it to the user
   - If the file already exists (HTTP 422 "sha" missing), append a timestamp to the filename (e.g., `image_1711872000.png`) and retry
   - On auth failure (HTTP 401/403), tell the user to check their `GITHUB_TOKEN` permissions (needs Contents read/write)

6. **Return the CDN URL** to the user in plain text:

```
Upload successful!
CDN URL: https://cdn.jsdelivr.net/gh/LingyiChen-AI/images/k8s-admin/images/2026/03/screenshot.png
```

## Batch Upload

When uploading multiple images, process them sequentially (GitHub API doesn't handle parallel writes to the same repo well). Show progress for each file.

## Important Notes

- Always write JSON payload to a temp file rather than passing base64 inline — avoids shell argument length limits.
- Always clean up temp files after upload.
- jsDelivr CDN has no CORS restrictions and works globally, making it ideal for embedding in articles, blogs, and external sites.
- jsDelivr caches aggressively. If the user needs to update an image, they should use a different filename rather than overwriting.
