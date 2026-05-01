from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from orchestrator import platform_graph, PlatformState

app = FastAPI()

# Mount the static folder to serve the frontend HTML
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/api/trigger-incident")
async def trigger_incident():
    """Endpoint triggered by the frontend when a 'CI Pipeline Fails'"""
    
    initial_state = PlatformState({
        "messages": [],
        "logs": ["🔥 CI Pipeline Failed! Triggering Autonomous Engineering Platform..."],
        "ci_status": "FAILED",
        "error_logs": "FATAL: Connection timeout to PostgreSQL cluster on port 5432.",
        "code_changes_made": False,
        "is_structural_change": False,
        "generated_adr": ""
    })
    
    # Run the LangGraph orchestration
    final_state = platform_graph.invoke(initial_state)
    
    return final_state

# Default route to serve the app
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")