import os
from typing import TypedDict, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

# ==========================================
# PHASE 1 & 3: VECTOR DB & MEMORY ENGINE
# ==========================================
class MockVectorDB:
    def __init__(self):
        self.memory = [
            "ADR-042: Switched from REST to GraphQL to reduce payload size.",
            "ADR-089: Implemented connection pooling using HikariCP to handle database timeout spikes during peak loads."
        ]
        
    def semantic_search(self, query: str) -> str:
        return self.memory[1] 

vector_db = MockVectorDB()

# ==========================================
# GRAPH STATE DEFINITION
# ==========================================
class PlatformState(TypedDict):
    messages: List[str]
    logs: List[str]  
    ci_status: str
    error_logs: str
    code_changes_made: bool
    is_structural_change: bool
    generated_adr: str

# ==========================================
# PHASE 2: CLI-NATIVE DEBUGGING AGENT
# ==========================================
def cli_debugging_agent(state: PlatformState) -> PlatformState:
    state["logs"].append("🛠️ CLI-Native Debugging Agent activated...")
    state["logs"].append(f"-> Analyzing logs: {state['error_logs']}")
    state["logs"].append("-> (Tool) Running grep for database config...")
    state["logs"].append("-> Found issue in `db_config.py`: Connection timeout due to single-thread bottleneck.")
    state["logs"].append("-> (Sandbox) Modifying connection logic to implement pooling...")
    state["logs"].append("-> (Sandbox) Running test suite...")
    state["logs"].append("-> Tests Passed! ✅")

    state["ci_status"] = "PASSED"
    state["code_changes_made"] = True
    state["is_structural_change"] = True 
    state["messages"].append("Bug fixed: Implemented DB connection pooling.")
    
    return state

# ==========================================
# ROUTING NODE (ORCHESTRATOR LOGIC)
# ==========================================
def check_architectural_impact(state: PlatformState) -> str:
    state["logs"].append("🧠 Orchestrator assessing code changes for structural impact...")
    if state["is_structural_change"]:
        state["logs"].append("-> Structural change detected. Routing to ADR Generation Agent.")
        return "generate_adr"
    else:
        state["logs"].append("-> Minor fix. Proceeding directly to Human Review.")
        return "human_review"

# ==========================================
# PHASE 4: ADR GENERATION AGENT (DRAFT)
# ==========================================
def adr_generation_agent(state: PlatformState) -> PlatformState:
    state["logs"].append("📝 ADR Generation Agent activated...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        state["logs"].append("❌ ERROR: GEMINI_API_KEY not found in environment.")
        return state
        
    # USING 1.5-FLASH FOR HIGH RATE LIMITS
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2, google_api_key=api_key)
    
    historical_context = vector_db.semantic_search("database connection pooling")
    
    system_prompt = f"""
    You are an expert Software Architect Agent.
    A structural change was just made to the codebase: {state['messages'][-1]}
    
    Here is a historical Architecture Decision Record (ADR) from this team to mimic their style:
    {historical_context}
    
    Generate a new ADR in Markdown format detailing this change. Include Context, Decision, and Consequences.
    """
    
    state["logs"].append("-> Generating ADR using Gemini API based on vector database context...")
    
    # USING HUMANMESSAGE TO PREVENT EMPTY CONTENT ERRORS
    response = llm.invoke([HumanMessage(content=system_prompt)])
    
    state["generated_adr"] = response.content
    return state

# ==========================================
# PHASE 5: HUMAN REVIEW & PULL REQUEST
# ==========================================
def human_review_node(state: PlatformState) -> PlatformState:
    state["logs"].append("🚀 Preparing Pull Request for Human Super-Node...")
    state["logs"].append("Awaiting human approval to merge... ✅")
    return state

# ==========================================
# BUILD THE LANGGRAPH ORCHESTRATOR
# ==========================================
def build_platform():
    workflow = StateGraph(PlatformState)
    
    workflow.add_node("cli_debugger", cli_debugging_agent)
    workflow.add_node("adr_generator", adr_generation_agent)
    workflow.add_node("human_review", human_review_node)
    
    workflow.add_edge(START, "cli_debugger")
    workflow.add_conditional_edges(
        "cli_debugger",
        check_architectural_impact,
        {"generate_adr": "adr_generator", "human_review": "human_review"}
    )
    workflow.add_edge("adr_generator", "human_review")
    workflow.add_edge("human_review", END)
    
    return workflow.compile()

platform_graph = build_platform()