# agent.py
import os
import sys
from pathlib import Path
import datetime
from dotenv import load_dotenv

# Note: Adjust these imports based on the specific ADK/framework you are utilizing
from google.adk.agents import Agent, LoopAgent
from google.adk.tools import agent_tool

# Load configuration
load_dotenv()
MODEL = os.getenv("MODEL", "gemini-2.0-flash")

# ==========================================
# 1. PLANNER LOOP (UPDATED FOR VIDEO)
# ==========================================
planner = Agent(
    name="Planner",
    model=MODEL,
    description="Creates a structured video storyboard and segment plan.",
    instruction="""
    You are a technical YouTube producer for an advanced engineering channel. Produce a clear Markdown storyboard outlining the video flow:
    - Video Title & 15-second Hook
    - 4-6 Main Video Segments (e.g., Whiteboard theory, Code walkthrough, Hardware demo)
    - Key technical takeaways for each segment
    - Specific screen recording targets (e.g., Ubuntu terminal execution, STM32CubeIDE pinout configuration, Altium schematic views)

    If 'codebase_context' exists in state, weave in specific file names or snippets.
    Return only the storyboard in Markdown.
    """,
    output_key="Tech_outline",
)

class OutlineValidationChecker(Agent):
    def __init__(self):
        super().__init__(
            name="OutlineValidationChecker",
            model=MODEL,
            description="Validates that the storyboard is usable.",
            instruction="""
            Check the storyboard in state 'Tech_outline'. If it has a title, hook, 4-6 distinct video segments, and screen recording targets, respond with exactly "ok".
            Otherwise respond with exactly "retry" and list the missing pieces.
            """,
            output_key="validation_result",
        )

robust_tech_planner = LoopAgent(
    name="RobustTechPlanner",
    description="Retries planning if validation fails.",
    sub_agents=[planner, OutlineValidationChecker()],
    max_iterations=3,
)

# ==========================================
# 2. WRITER LOOP (UPDATED FOR VIDEO)
# ==========================================
tech_writer = Agent(
    name="TechWriter",
    model=MODEL,
    description="Writes a technical YouTube script from the storyboard.",
    instruction="""
    Write a complete YouTube video script from the storyboard in 'Tech_outline'.

    Guidelines:
    - Audience: Experienced hardware and software engineers. Skip basic definitions.
    - Format: Use a two-column style in Markdown. Use bold bracketed text for visuals like **[VISUAL: Screen record VS Code terminal]** or **[VISUAL: B-Roll of soil moisture tensiometer node]**, followed by the exact spoken audio script.
    - Explain the architectural 'how' and 'why', not just what to click.
    - Include concise C/C++ or React code snippets to be displayed as screen overlays.
    - Output only the final script in Markdown (no fence around the whole post).
    """,
    output_key="tech_post",
)

class TechPostValidationChecker(Agent):
    def __init__(self):
        super().__init__(
            name="TechPostValidationChecker",
            model=MODEL,
            description="Validates the final video script.",
            instruction="""
            Check the 'tech_post' for: visual cues in brackets, spoken audio script, code overlays, and deep technical clarity matching the storyboard.
            If it passes, respond with exactly "ok".
            Otherwise respond with exactly "retry" and list the missing pieces.
            """,
            output_key="validation_result",
        )

robust_tech_writer = LoopAgent(
    name="RobustTechWriter",
    description="Retries writing if validation fails.",
    sub_agents=[tech_writer, TechPostValidationChecker()],
    max_iterations=3,
)

# ==========================================
# 3. ROOT COORDINATOR
# ==========================================
planner_tool = agent_tool.AgentTool(agent=robust_tech_planner)
writer_tool = agent_tool.AgentTool(agent=robust_tech_writer)

root_agent = Agent(
    name="Techie",
    model=MODEL,
    description="Minimal multi-agent blogger that plans and writes.",
    instruction=f"""
    If the user gives a topic:
    1) Call the planner tool to generate the outline.
    2) Call the writer tool to produce the full draft.
    3) End with 3 alternate titles and 2 tweet-length hooks.

    If the trends tool fails or times out, continue with a sensible outline and draft anyway.
    
    Date: {datetime.datetime.now().strftime("%Y-%m-%d")}
    """,
    tools=[planner_tool, writer_tool],
)

# ==========================================
# 4. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import asyncio
    from google.adk.runners import InMemoryRunner
    from google.genai import types

# ==========================================
    # 4. EXECUTION ENTRY POINT
    # ==========================================
    if __name__ == "__main__":
        import sys
        import asyncio
        from google.adk.runners import InMemoryRunner
        from google.genai import types
        
        # 1. Define the global context for the AS9100D QMS playlist
        project_context = """
        # Building an Enterprise AS9100D QMS Compliance Dashboard for electronics manufacturing
        **Tech Stack:** React (TypeScript), Tailwind CSS, Node.js (Express), Microsoft SQL Server

        ## Course Overview
        In this comprehensive tutorial, you will build a production-ready Quality Management System (QMS) designed to meet strict aerospace (AS9100D) and ISO 9001 manufacturing standards. You will learn how to build robust React dashboards, connect them to a local Microsoft SQL Server backend using Express, and implement strict data-integrity rules to satisfy compliance auditors.
        """
        
        # 2. Grab the specific sub-module from the terminal
        sub_module = sys.argv[1] if len(sys.argv) > 1 else "1.1 Introduction to AS9100D & ISO 9001 Data Requirements"
        
        # 3. Combine them so the agent understands the big picture AND the specific task
        combined_prompt = f"GLOBAL CONTEXT:\n{project_context}\n\nCURRENT VIDEO TOPIC:\n{sub_module}"
        print(f"Starting workflow for: {sub_module}\n")
        
        # Initialize the runner and an isolated session
        runner = InMemoryRunner(agent=root_agent, app_name='tech_blog')
        session = asyncio.run(runner.session_service.create_session(app_name='tech_blog', user_id='user'))
        
        # Format the combined prompt as a Content object
        content = types.Content(role='user', parts=[types.Part.from_text(text=combined_prompt)]) 
    final_text = ""
    
    # Execute the agent and capture its output events
    for event in runner.run(user_id='user', session_id=session.id, new_message=content):
        if getattr(event, 'content', None) and event.content.parts:
            text_chunk = event.content.parts[0].text
            if text_chunk:
                final_text += text_chunk + "\n"
                # Print progress to the terminal
                print(f"** {getattr(event, 'author', 'Agent')}: {text_chunk}")

    # Save the output to the dedicated folder
    output_path = Path("output") / f"draft_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)
        
    print(f"\nWorkflow complete. Draft saved to {output_path}")