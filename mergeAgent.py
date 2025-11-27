# ==============================================================================
# 1. ADK and Utility Imports
# ==============================================================================
import os
import json
import re
import time
from dotenv import load_dotenv
from google.genai import types
import asyncio
import argparse 

# Import necessary ADK components
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner

# ==============================================================================
# 2. Environment Setup
# ==============================================================================
load_dotenv()

output_filename = "merged_output.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# ==============================================================================
# 3. Configure Model & Retry Options
# ==============================================================================
http_retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=2,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

MAX_JSON_RETRIES = 3

# ==============================================================================
# 4. Helper Function: Clean JSON
# ==============================================================================
def clean_json_text(text: str) -> str:
    match = re.search(r'```(?:json)?\s*({.*})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

# ==============================================================================
# 5. Define the ADK Agent
# ==============================================================================

def create_merge_agent(system_prompt: str) -> LlmAgent:
    """Creates the ADK LlmAgent optimized for merging two datasets."""
    
    merge_agent = LlmAgent(
        name="MergeSpecialistAgent",
        model=Gemini(
            model="gemini-2.5-flash-lite", 
            retry_options=http_retry_config,
            # CRITICAL: Forces JSON output
            generation_config={
                "response_mime_type": "application/json"
            }
        ), 
        instruction=system_prompt,
        tools=[], # No search tool needed for internal merging
    )
    
    return merge_agent

# ==============================================================================
# 6. Main Execution using ADK Runner
# ==============================================================================
async def main(master_path: str, child_path: str):
    
    # 1. Load System Prompt
    try:
        with open("merge_system_prompt.md", "r") as f:
            system_prompt_content = f.read()
    except FileNotFoundError:
        print("Error: merge_system_prompt.md not found.")
        return

    # 2. Load Master Log
    try:
        with open(master_path, "r") as f:
            master_content = f.read()
    except FileNotFoundError:
        print(f"Error: Master file '{master_path}' not found.")
        return

    # 3. Load Child Data
    try:
        with open(child_path, "r") as f:
            child_content = f.read()
    except FileNotFoundError:
        print(f"Error: Child file '{child_path}' not found.")
        return

    # 4. Construct the Combined Message
    user_message = (
        f"Please merge the following two datasets based on the system instructions.\n\n"
        f"--- MASTER LOG ---\n{master_content}\n\n"
        f"--- CHILD DATA ---\n{child_content}"
    )
    
    # 5. THE RETRY LOOP
    for attempt in range(1, MAX_JSON_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_JSON_RETRIES} ---")
        
        agent = create_merge_agent(system_prompt_content)
        runner = InMemoryRunner(agent=agent)

        try:
            print("🤖 Merge Agent is processing...")
            response = await runner.run_debug(user_message)
            
            # Extract Response
            final_event = response[-1]
            raw_text = ""

            if final_event.content and final_event.content.parts:
                final_part = final_event.content.parts[0]
                if final_part.text:
                    raw_text = final_part.text
                elif final_part.function_call and final_part.function_call.args:
                    raw_text = json.dumps(final_part.function_call.args, indent=4)
                else:
                    raw_text = str(final_event)
            else:
                raw_text = str(final_event)

            # Clean and Parse
            cleaned_json_string = clean_json_text(raw_text)
            json_obj = json.loads(cleaned_json_string)
            
            print("✅ Valid JSON generated.")
            
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(json_obj, f, indent=2)
            print(f"✅ Successfully saved merged data to {output_filename}")
            return 

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Parse Error on attempt {attempt}: {e}")
            time.sleep(2)
            continue 
        
        except Exception as e:
            print(f"❌ Unexpected Error on attempt {attempt}: {e}")
            return

    print("\n❌ Failed to generate valid JSON after max retries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge Master Log and Child Data.")
    parser.add_argument("master_file", help="Path to the Master Log JSON")
    parser.add_argument("child_file", help="Path to the Child Data JSON")
    args = parser.parse_args()

    asyncio.run(main(args.master_file, args.child_file))