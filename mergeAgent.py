import os
import json
import re
import time
import asyncio
import argparse
import uuid
from dotenv import load_dotenv
from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.apps.app import App, EventsCompactionConfig

load_dotenv()
output_filename = "merged_output.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

http_retry_config = types.HttpRetryOptions(attempts=5, exp_base=2, initial_delay=1, http_status_codes=[429, 500, 503])
MAX_JSON_RETRIES = 3

# [FIXED FUNCTION] - Handles Lists [] and Objects {}
def clean_json_text(text: str) -> str:
    """
    Robustly extracts JSON from Markdown. 
    Handles both objects {...} and lists [...].
    """
    # 1. Regex Match: Looks for ```json ... ``` containing [ or {
    # The [\[{] part means "match either '[' or '{'"
    match = re.search(r'```(?:json)?\s*([\[{].*?[\]}])\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    
    # 2. Manual Fallback: If regex fails (e.g. malformed ending), try stripping tags manually
    cleaned = text.strip()
    
    # Remove start tag
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    
    # Remove end tag
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
        
    return cleaned

def create_merge_agent(system_prompt: str) -> LlmAgent:
    return LlmAgent(
        name="MergeSpecialistAgent",
        model=Gemini(
            model="gemini-2.5-flash-lite", 
            retry_options=http_retry_config,
            generation_config={"response_mime_type": "application/json"}
        ), 
        instruction=system_prompt,
        tools=[], 
    )

async def main(master_path: str, child_path: str, session_id: str):
    
    # 1. Load and Validate Inputs
    try:
        with open("merge_system_prompt.md", "r") as f: system_prompt_content = f.read()
    except FileNotFoundError:
        print("❌ Error: merge_system_prompt.md not found.")
        return

    try:
        with open(master_path, "r") as f: master_content = f.read()
        with open(child_path, "r") as f: child_content = f.read()
        
        if not master_content.strip() or not child_content.strip():
            print("❌ Error: Input files (master or child) are empty.")
            return

    except FileNotFoundError as e:
        print(f"❌ Error loading data files: {e}")
        return

    # 2. Config & Persistence
    compaction_config = EventsCompactionConfig(compaction_interval=2, overlap_size=1)
    db_url = "sqlite:///osdu_pipeline.db"
    session_service = DatabaseSessionService(db_url=db_url)

    # 3. Init App/Runner
    APP_NAME = "merge_app"
    agent = create_merge_agent(system_prompt_content)
    app = App(name=APP_NAME, root_agent=agent, events_compaction_config=compaction_config)
    runner = Runner(app=app, session_service=session_service)

    # 4. Create Session Explicitly
    try:
        await session_service.create_session(app_name=APP_NAME, user_id="osdu_user", session_id=session_id)
        print(f"✅ Session Created: {session_id}")
    except Exception:
        pass 

    current_text = (
        f"Please merge the following two datasets based on the system instructions.\n\n"
        f"--- MASTER LOG ---\n{master_content}\n\n"
        f"--- CHILD DATA ---\n{child_content}"
    )
    
    print(f"🚀 Starting Merge Agent (Session: {session_id})...")
    
    for attempt in range(1, MAX_JSON_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_JSON_RETRIES} ---")

        current_message = types.Content(role="user", parts=[types.Part(text=current_text)])

        try:
            print("🤖 Merge Agent is processing...")
            raw_text = ""
            
            async for event in runner.run_async(user_id="osdu_user", session_id=session_id, new_message=current_message):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text: 
                            raw_text += part.text
                        elif part.function_call: 
                            raw_text += json.dumps(part.function_call.args)
                
            # Check for empty response
            if not raw_text.strip():
                print("⚠️ Warning: Model returned empty response.")
                # Try to extract from previous turns or just retry
                time.sleep(2)
                continue

            # [DEBUG] Print the first 50 chars to verify cleanup works
            # print(f"DEBUG Raw Start: {repr(raw_text[:50])}")

            cleaned_json_string = clean_json_text(raw_text)
            
            # print(f"DEBUG Cleaned Start: {repr(cleaned_json_string[:50])}")

            json_obj = json.loads(cleaned_json_string)
            
            print("✅ Valid JSON generated.")
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(json_obj, f, indent=2)
            print(f"✅ Successfully saved merged data to {output_filename}")
            return 

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Parse Error on attempt {attempt}: {e}")
            # print(f"   (Partial Content: {raw_text[:100]}...)") 
            current_text = f"Previous attempt failed with JSON error: {e}. Please correct syntax (ensure no markdown) and return valid JSON."
            time.sleep(2)
            continue 
        
        except Exception as e:
            print(f"❌ Unexpected Error on attempt {attempt}: {e}")
            time.sleep(2)
            continue

    print("\n❌ Failed to generate valid JSON after max retries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge Master Log and Child Data.")
    parser.add_argument("master_file", help="Path to the Master Log JSON")
    parser.add_argument("child_file", help="Path to the Child Data JSON")
    args = parser.parse_args()

    DUMMY_SESSION = f"merge-manual-{str(uuid.uuid4())[:8]}"
    asyncio.run(main(args.master_file, args.child_file, DUMMY_SESSION))