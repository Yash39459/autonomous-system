import os
import base64
import httpx
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure environment variables (like GEMINI_API_KEY) are freshly loaded
load_dotenv(override=True)

from orchestrator import platform_graph, PlatformState

app = FastAPI(title="Autonomous Engineering Platform", version="2.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# REQUEST MODELS
# ==========================================
class GithubImportRequest(BaseModel):
    repo_url: str
    file_path: str = ""  # optional specific file path

class MergeRequest(BaseModel):
    commit_message: str
    patch_content: str
    adr_content: str
    file_name: str

# ==========================================
# HELPER: Run orchestration
# ==========================================
def run_orchestration(code_content: str = "", file_name: str = "simulated", source_type: str = "simulated", error_logs: str = ""):
    initial_state = PlatformState({
        "messages": [],
        "logs": [f"🔥 Incident detected! Triggering Autonomous Engineering Platform..."],
        "ci_status": "FAILED",
        "error_logs": error_logs or "FATAL: Connection timeout to PostgreSQL cluster on port 5432.",
        "code_changes_made": False,
        "is_structural_change": False,
        "generated_adr": "",
        "code_content": code_content,
        "file_name": file_name,
        "source_type": source_type,
        "detected_issues": [],
        "suggested_fixes": [],
        "diff_content": "",
        "patch_content": "",
        "commit_message": "",
        "analysis_summary": "",
        "severity": "low",
    })
    return platform_graph.invoke(initial_state)

# ==========================================
# ENDPOINTS
# ==========================================

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.post("/api/trigger-incident")
async def trigger_incident():
    """Simulate a CI pipeline failure (demo mode)."""
    final_state = run_orchestration(source_type="simulated")
    return final_state

@app.post("/api/import-file")
async def import_file(file: UploadFile = File(...)):
    """Accept a code file upload and run the autonomous pipeline on it."""
    allowed_extensions = {".py", ".js", ".ts", ".java", ".go", ".rb", ".cpp", ".c", ".cs", ".php", ".rs", ".kt", ".swift"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Supported: {', '.join(allowed_extensions)}"
        )
    
    content_bytes = await file.read()
    
    if len(content_bytes) > 500_000:  # 500KB limit
        raise HTTPException(status_code=400, detail="File too large. Max size: 500KB")
    
    try:
        code_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding not supported. Please use UTF-8.")
    
    final_state = run_orchestration(
        code_content=code_content,
        file_name=file.filename,
        source_type="upload",
        error_logs=f"Code review triggered on uploaded file: {file.filename}"
    )
    return final_state

@app.post("/api/import-github")
async def import_github(request: GithubImportRequest):
    """Fetch a file from a public GitHub repo and run the autonomous pipeline."""
    repo_url = request.repo_url.strip().rstrip("/")
    
    # Parse owner/repo from various GitHub URL formats
    if "github.com/" in repo_url:
        parts = repo_url.split("github.com/")[-1].split("/")
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL. Expected: https://github.com/owner/repo")
        owner, repo = parts[0], parts[1].replace(".git", "")
    else:
        raise HTTPException(status_code=400, detail="URL must be a GitHub repository URL.")
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if gh_token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {gh_token}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # If a specific file path was given, fetch that file
        if request.file_path:
            file_path = request.file_path.lstrip("/")
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            resp = await client.get(api_url, headers=headers)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"File '{file_path}' not found in {owner}/{repo}")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")
            
            data = resp.json()
            if data.get("type") != "file":
                raise HTTPException(status_code=400, detail="Path points to a directory, not a file.")
            
            code_content = base64.b64decode(data["content"]).decode("utf-8")
            file_name = data["name"]
        else:
            # Auto-detect: list root contents and pick a good code file
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
            resp = await client.get(api_url, headers=headers)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Repository '{owner}/{repo}' not found or is private.")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")
            
            contents = resp.json()
            if not isinstance(contents, list):
                raise HTTPException(status_code=400, detail="Unexpected GitHub API response.")
            
            code_extensions = {".py", ".js", ".ts", ".java", ".go", ".rb", ".rs"}
            preferred_names = ["main", "app", "server", "index", "api", "core", "utils"]
            
            chosen = None
            for item in contents:
                if item["type"] != "file":
                    continue
                ext = os.path.splitext(item["name"])[1].lower()
                if ext not in code_extensions:
                    continue
                base = os.path.splitext(item["name"])[0].lower()
                if any(p in base for p in preferred_names):
                    chosen = item
                    break
            
            if not chosen:
                # Just take the first code file found
                for item in contents:
                    ext = os.path.splitext(item.get("name", ""))[1].lower()
                    if item["type"] == "file" and ext in code_extensions:
                        chosen = item
                        break
            
            if not chosen:
                raise HTTPException(
                    status_code=404,
                    detail="No supported code files found in repo root. Try specifying a file path."
                )
            
            # Fetch the chosen file
            file_resp = await client.get(chosen["url"], headers=headers)
            if file_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch file content from GitHub.")
            
            file_data = file_resp.json()
            code_content = base64.b64decode(file_data["content"]).decode("utf-8")
            file_name = chosen["name"]
    
    final_state = run_orchestration(
        code_content=code_content,
        file_name=file_name,
        source_type=f"github:{owner}/{repo}",
        error_logs=f"GitHub import: {owner}/{repo}/{file_name}"
    )
    return final_state

@app.post("/api/approve-merge")
async def approve_merge(request: MergeRequest):
    """
    Simulate a real merge: returns a downloadable .patch file and git instructions.
    In a production system, this would call the GitHub API to merge the PR.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    branch_name = f"autonomous/fix-{request.file_name.split('.')[0].lower().replace(' ', '-')}-{timestamp}"
    
    # Build a realistic .patch file
    patch_content = f"""From autonomous-bot@platform.ai {datetime.utcnow().strftime('%a %b %d %H:%M:%S %Y')}
From: Autonomous Engineering Platform <bot@platform.ai>
Date: {datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')}
Subject: [PATCH] {request.commit_message}
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

{request.patch_content}

---
 1 file changed
 Generated by Autonomous Engineering Platform v2.0
"""

    # Build git commands for the developer
    git_commands = f"""#!/bin/bash
# ============================================================
# Autonomous Engineering Platform — Merge Instructions
# Generated: {datetime.utcnow().isoformat()}Z
# ============================================================

# 1. Create and switch to the fix branch
git checkout -b {branch_name}

# 2. Apply the patch
git apply --stat autonomous_fix_{timestamp}.patch
git apply autonomous_fix_{timestamp}.patch

# 3. Stage and commit
git add -A
git commit -m "{request.commit_message}"

# 4. Push to remote
git push origin {branch_name}

# 5. (Optional) Create PR via GitHub CLI
gh pr create \\
  --title "{request.commit_message}" \\
  --body "## Autonomous Fix\\n\\nGenerated by Autonomous Engineering Platform\\n\\n### Changes\\n{request.commit_message}\\n\\n### ADR\\nSee attached ADR for architectural context." \\
  --base main \\
  --head {branch_name}

echo "✅ Merge complete!"
"""

    return {
        "success": True,
        "branch_name": branch_name,
        "timestamp": timestamp,
        "patch_file_content": patch_content,
        "git_commands": git_commands,
        "merge_summary": {
            "commit": request.commit_message,
            "branch": branch_name,
            "files_changed": 1,
            "insertions": patch_content.count("+"),
            "deletions": patch_content.count("-"),
        }
    }

@app.get("/api/export-adr")
async def export_adr(content: str = "", filename: str = "ADR.md"):
    """Return an ADR as a downloadable markdown file."""
    if not content:
        content = "# No ADR content provided"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.get("/api/health")
async def health():
    return {
        "status": "operational",
        "version": "2.0.0",
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "github_token_configured": bool(os.environ.get("GITHUB_TOKEN")),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }