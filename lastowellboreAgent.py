import json
import os
import asyncio
import re
import logging
from dotenv import load_dotenv

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner

# --- Existing Project Imports (Mocked for standalone use) ---
try:
    from utils.service import convert_las_to_osdu_records
    from utils.models import FileValidationError
    from utils.utils import logger
except ImportError:
    # Fallback if files are missing
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    FileValidationError = Exception
    def convert_las_to_osdu_records(las_content, wellbore_id, config_content):
        return {"wellbore_record": {"id": wellbore_id}, "welllog_record": {"id": wellbore_id}}

# --- Setup Environment ---
load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    logger.warning("⚠️ GEMINI_API_KEY not found in environment variables.")


# --- 1. Define the Custom Tool ---
# This remains global as it is a stateless function definition
def convert_las_tool(las_file_path: str, wellbore_id: str, config_content: dict) -> dict:
    """Reads a LAS file from a path and converts it to OSDU records."""
    try:
        logger.info(f"Tool is reading file from: {las_file_path}")
        
        if not os.path.exists(las_file_path):
            return {"status": "error", "error_message": f"File not found at path: {las_file_path}"}

        # 1. Read the file content inside the tool
        with open(las_file_path, 'r', encoding='latin-1') as f:
            las_content_str = f.read()

        # 2. Call the domain service
        records = convert_las_to_osdu_records(
            las_content=las_content_str,
            wellbore_id=wellbore_id,
            config_content=config_content
        )
        
        # 3. Serialize results
        wb_data = records["wellbore_record"]
        wl_data = records["welllog_record"]
        
        # Helper to convert objects to dicts if needed
        if hasattr(wb_data, '__dict__'): wb_data = vars(wb_data)
        if hasattr(wl_data, '__dict__'): wl_data = vars(wl_data)

        result_data = {
            "wellbore": wb_data,
            "welllog": wl_data
        }
        
        return {"status": "success", "data": result_data}

    except (ValueError, TypeError, FileValidationError) as e:
        logger.error(f"Tool Validation Error: {e}")
        return {"status": "error", "error_message": str(e)}
    except Exception as e:
        logger.error(f"Tool Internal Error: {e}")
        return {"status": "error", "error_message": f"Unexpected conversion error: {str(e)}"}


# --- 2. Helper Functions ---

def extract_json_from_text(text: str):
    """Helper to extract JSON from LLM response."""
    print("##################################")
    #print(text)
    # text = re.sub(r'```json\s*', '', text) 
    # text = re.sub(r'```\s*', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if match: return json.loads(match.group(1))
        match = re.search(r'({.*})', text, re.DOTALL)
        if match: return json.loads(match.group(1))
        return None


# --- 3. Main Execution Logic (The Fix) ---

async def process_las_file(las_path: str, config_path: str, wellbore_id: str):
    """Orchestrates the execution."""
    welllog_filename = None
    # 1. Read Config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception as e:
        logger.error(f"Config file error: {e}")
        return

    # 2. Initialize Model and Agent INSIDE the async function
    # This ensures the HTTP session is attached to the current event loop
    retry_config = types.HttpRetryOptions(
        attempts=3,
        exp_base=2,
        initial_delay=1,
        http_status_codes=[429, 500, 503],
    )

    model = Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config)

    agent = LlmAgent(
        name="las_processing_agent",
        model=model, 
        instruction="""You are a specialized technical assistant for OSDU data ingestion.
        
        Your goal is to convert LAS files into JSON records.
        
        STRICTLY FOLLOW THESE STEPS:
        1. Receive the `LAS File Path`, `Wellbore ID`, and `Config` from the user.
        2. Call the `convert_las_tool` passing the exact file path provided. Do NOT try to read the file yourself.
        3. Check the "status" field in the tool's response:
           - If "status" is "error": Stop and report the "error_message" to the user.
           - If "status" is "success": Extract the "data" (containing wellbore and welllog objects).
        4. Return the final JSON structure clearly. Output ONLY the valid JSON structure in your final response.
        """,
        tools=[convert_las_tool],
    )

    runner = InMemoryRunner(agent=agent)
    print(f"🚀 Starting Agent for Wellbore: {wellbore_id}...")

    # 3. Construct Prompt
    user_prompt = (
        f"Please convert the LAS file located at this path: {las_path}\n"
        f"Wellbore ID: {wellbore_id}\n"
        f"Config: {json.dumps(config_data)}"
    )

    # 4. Execute Agent
    try:
        response_events = await runner.run_debug(user_prompt)
        
        print("🤖 Agent finished execution.")
        
        # 5. Extract Text from Events
        final_text = ""
        for event in response_events:
            if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_text += part.text
        
        if not final_text:
            print("⚠️ Agent finished but returned no text.")
            return

        # 6. Parse JSON
        final_json = extract_json_from_text(final_text)
        
        if final_json and "wellbore" in final_json:
            wellbore_filename = f"{wellbore_id}-wellbore.json"
            welllog_filename = f"{wellbore_id}-welllog.json"

            with open(wellbore_filename, 'w', encoding='utf-8') as f:
                json.dump(final_json["wellbore"], f, indent=4)
            
            if "welllog" in final_json:
                with open(welllog_filename, 'w', encoding='utf-8') as f:
                    json.dump(final_json["welllog"], f, indent=4)

            print(f"✅ Success! Files generated:")
            print(f"   - {wellbore_filename}")
            if "welllog" in final_json: print(f"   - {welllog_filename}")
        else:
            print("⚠️ Agent responded, but valid JSON was not found.")
            print("Response Preview:", final_text[:500])

    except Exception as e:
        logger.error(f"Agent Execution Error: {e}")
        import traceback
        traceback.print_exc()
    return welllog_filename


if __name__ == "__main__":
    # Adjust paths for your local environment
    LAS_FILE_PATH = os.path.abspath("test_data/7_1-1.las") 
    CONFIG_FILE_PATH = os.path.abspath("test_data/sample_config.json")
    WELLBORE_ID = "well-1234"

    if os.path.exists(LAS_FILE_PATH) and os.path.exists(CONFIG_FILE_PATH):
        asyncio.run(process_las_file(LAS_FILE_PATH, CONFIG_FILE_PATH, WELLBORE_ID))
    else:
        print("❌ Error: Input files not found.")
        print(f"Checked: {LAS_FILE_PATH}")
        print(f"Checked: {CONFIG_FILE_PATH}")