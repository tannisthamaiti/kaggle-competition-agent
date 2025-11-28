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
from google.adk.tools import google_search

load_dotenv()
output_filename = "childLogs.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

http_retry_config = types.HttpRetryOptions(attempts=5, exp_base=2, initial_delay=1, http_status_codes=[429, 500, 503])
MAX_JSON_RETRIES = 3

def clean_json_text(text: str) -> str:
    match = re.search(r'```(?:json)?\s*({.*})\s*```', text, re.DOTALL)
    if match: return match.group(1)
    return text.strip()

def create_search_agent(system_prompt: str) -> LlmAgent:
    return LlmAgent(
        name="SearchSpecialistAgent",
        model=Gemini(
            model="gemini-2.5-flash-lite", 
            retry_options=http_retry_config,
            generation_config={"response_mime_type": "application/json"}
        ), 
        instruction=system_prompt,
        tools=[google_search],
    )

async def main(input_file_path: str, session_id: str):
    try:
        with open("PROMPT/system_prompt.md", "r") as f: system_prompt_content = f.read()
    except FileNotFoundError:
        print("Error: system_prompt.md not found.")
        return

    try:
        with open(input_file_path, "r") as f: input_json_content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{input_file_path}' was not found.")
        return

    # 1. Config & Persistence
    compaction_config = EventsCompactionConfig(compaction_interval=2, overlap_size=1)
    db_url = "sqlite:///osdu_pipeline.db"
    session_service = DatabaseSessionService(db_url=db_url)

    # 2. Init App/Runner
    APP_NAME = "search_app"
    agent = create_search_agent(system_prompt_content)
    app = App(name=APP_NAME, root_agent=agent, events_compaction_config=compaction_config)
    runner = Runner(app=app, session_service=session_service)

    # [FIX 1] EXPLICITLY CREATE SESSION
    try:
        await session_service.create_session(app_name=APP_NAME, user_id="osdu_user", session_id=session_id)
        print(f"✅ Session Created: {session_id}")
    except Exception:
        pass

    current_text = f"Here is the input data:\n{input_json_content}"
    print(f"🚀 Starting Search Agent (Session: {session_id})...")

    for attempt in range(1, MAX_JSON_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_JSON_RETRIES} ---")
        
        # [FIX 2] Wrap in types.Content
        current_message = types.Content(role="user", parts=[types.Part(text=current_text)])
        
        try:
            raw_text = ""
            async for event in runner.run_async(user_id="osdu_user", session_id=session_id, new_message=current_message):
                if event.content and event.content.parts:
                    final_part = event.content.parts[0]
                    if final_part.text: raw_text += final_part.text
                    elif final_part.function_call: raw_text += json.dumps(final_part.function_call.args)

            cleaned_json_string = clean_json_text(raw_text)
            json_obj = json.loads(cleaned_json_string)
            
            print("✅ Valid JSON received.")
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(json_obj, f, indent=2)
            print(f"✅ Successfully saved to {output_filename}")
            return

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Parse Error on attempt {attempt}: {e}")
            current_text = f"Your previous response was invalid JSON. Error: {str(e)}. Please correct it and return ONLY valid JSON."
            time.sleep(2)
            continue
        
        except Exception as e:
            print(f"❌ Unexpected Error on attempt {attempt}: {e}")
            return

    print("\n❌ Failed to generate valid JSON after max retries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a well log JSON file with ADK.")
    parser.add_argument("input_file", help="Path to the input JSON file")
    args = parser.parse_args()
    
    DUMMY_SESSION = f"search-manual-{str(uuid.uuid4())[:8]}"
    asyncio.run(main(args.input_file, DUMMY_SESSION))