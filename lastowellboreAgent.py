import json
import os
import asyncio
import re
import logging
import uuid
from dotenv import load_dotenv

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner 
from google.adk.sessions import DatabaseSessionService 

# --- Existing Project Imports (Mocked) ---
try:
    from utils.service import convert_las_to_osdu_records
    from utils.models import FileValidationError
    from utils.utils import logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    FileValidationError = Exception
    def convert_las_to_osdu_records(las_content, wellbore_id, config_content):
        return {"wellbore_record": {"id": wellbore_id}, "welllog_record": {"id": wellbore_id}}

load_dotenv()

# --- 1. Define Tool (Unchanged) ---
def convert_las_tool(las_file_path: str, wellbore_id: str, config_content: dict) -> dict:
    """Reads a LAS file from a path and converts it to OSDU records."""
    try:
        logger.info(f"Tool is reading file from: {las_file_path}")
        if not os.path.exists(las_file_path):
            return {"status": "error", "error_message": f"File not found: {las_file_path}"}

        with open(las_file_path, 'r', encoding='latin-1') as f:
            las_content_str = f.read()

        records = convert_las_to_osdu_records(las_content_str, wellbore_id, config_content)
        wb_data = records["wellbore_record"]
        wl_data = records["welllog_record"]
        
        if hasattr(wb_data, '__dict__'): wb_data = vars(wb_data)
        if hasattr(wl_data, '__dict__'): wl_data = vars(wl_data)

        return {"status": "success", "data": {"wellbore": wb_data, "welllog": wl_data}}
    except Exception as e:
        logger.error(f"Tool Error: {e}")
        return {"status": "error", "error_message": str(e)}

# --- 2. Helper (Unchanged) ---
def extract_json_from_text(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if match: return json.loads(match.group(1))
        match = re.search(r'({.*})', text, re.DOTALL)
        if match: return json.loads(match.group(1))
        return None

# --- 3. Main Execution (Fixed) ---
async def process_las_file(las_path: str, config_path: str, wellbore_id: str, session_id: str):
    welllog_filename = None
    
    # 1. Read Config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception as e:
        logger.error(f"Config file error: {e}")
        return

    # 2. Setup Persistence
    db_url = "sqlite:///osdu_pipeline.db"
    session_service = DatabaseSessionService(db_url=db_url)

    # 3. Initialize Agent
    retry_config = types.HttpRetryOptions(attempts=3, exp_base=2, initial_delay=1, http_status_codes=[429, 500, 503])
    model = Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config)

    agent = LlmAgent(
        name="las_processing_agent",
        model=model, 
        instruction="""Convert LAS files to JSON using `convert_las_tool`.
        1. Call `convert_las_tool`.
        2. If status is error, stop.
        3. If success, output ONLY the valid JSON 'data' object.""",
        tools=[convert_las_tool],
    )

    # 4. Initialize Runner
    APP_NAME = "osdu_ingest"
    runner = Runner(agent=agent, session_service=session_service, app_name=APP_NAME)
    
    # [FIX 1] EXPLICITLY CREATE SESSION
    try:
        await session_service.create_session(app_name=APP_NAME, user_id="osdu_user", session_id=session_id)
        print(f"✅ Session Created: {session_id}")
    except Exception:
        # If resuming, session might exist, so we catch and ignore
        pass

    print(f"🚀 Starting Agent for Wellbore: {wellbore_id}...")

    # 5. Prepare Message
    user_prompt_text = (
        f"Please convert the LAS file located at this path: {las_path}\n"
        f"Wellbore ID: {wellbore_id}\n"
        f"Config: {json.dumps(config_data)}"
    )
    
    # [FIX 2] Wrap in types.Content
    user_message = types.Content(role="user", parts=[types.Part(text=user_prompt_text)])

    try:
        final_text = ""
        # 6. Run Async
        async for event in runner.run_async(user_id="osdu_user", session_id=session_id, new_message=user_message):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text
        
        print("🤖 Agent finished execution.")
        
        final_json = extract_json_from_text(final_text)
        if final_json and "wellbore" in final_json:
            wellbore_filename = f"{wellbore_id}-wellbore.json"
            welllog_filename = f"{wellbore_id}-welllog.json"

            with open(wellbore_filename, 'w', encoding='utf-8') as f:
                json.dump(final_json["wellbore"], f, indent=4)
            if "welllog" in final_json:
                with open(welllog_filename, 'w', encoding='utf-8') as f:
                    json.dump(final_json["welllog"], f, indent=4)

            print(f"✅ Success! Files generated: {wellbore_filename}")
        else:
            print("⚠️ Agent responded, but valid JSON was not found.")

    except Exception as e:
        logger.error(f"Agent Execution Error: {e}")
        import traceback
        traceback.print_exc()
    return welllog_filename

if __name__ == "__main__":
    LAS_FILE_PATH = os.path.abspath("test_data/7_1-1.las") 
    CONFIG_FILE_PATH = os.path.abspath("test_data/sample_config.json")
    WELLBORE_ID = "well-1234"
    DUMMY_SESSION = f"test-session-{str(uuid.uuid4())[:8]}"

    if os.path.exists(LAS_FILE_PATH) and os.path.exists(CONFIG_FILE_PATH):
        asyncio.run(process_las_file(LAS_FILE_PATH, CONFIG_FILE_PATH, WELLBORE_ID, DUMMY_SESSION))