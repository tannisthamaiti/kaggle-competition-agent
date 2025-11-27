# ==============================================================================
# 1. ADK and Utility Imports
# ==============================================================================
import os
import json
import re
import time  # Added for backoff sleep
from dotenv import load_dotenv
from google.genai import types
import asyncio
import argparse 

# Import necessary ADK components
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search

# ==============================================================================
# 2. Environment Setup and Tool Definition
# ==============================================================================
load_dotenv()

output_filename = "childLogs.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# ==============================================================================
# 3. Configure Model & Retry Options
# ==============================================================================
# Network/API level retries (for 500/429 errors)
http_retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=2,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# Parsing level retries (for invalid JSON)
MAX_JSON_RETRIES = 3

# ==============================================================================
# 4. Helper Function: Clean JSON
# ==============================================================================
def clean_json_text(text: str) -> str:
    """
    Removes Markdown code blocks to ensure the file contains only raw JSON.
    """
    match = re.search(r'```(?:json)?\s*({.*})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

# ==============================================================================
# 5. Define the ADK Agent
# ==============================================================================

def create_search_agent(system_prompt: str) -> LlmAgent:
    """Creates and returns the ADK LlmAgent with the Google Search tool."""
    
    search_agent = LlmAgent(
        name="SearchSpecialistAgent",
        model=Gemini(
            model="gemini-2.5-flash-lite", 
            retry_options=http_retry_config,
            # CRITICAL: This forces the model to attempt JSON output natively
            generation_config={
                "response_mime_type": "application/json"
            }
        ), 
        instruction=system_prompt,
        tools=[google_search],
    )
    
    return search_agent

# ==============================================================================
# 6. Main Execution using ADK Runner
# ==============================================================================
async def main(input_file_path: str):
    
    # 1. Load the system prompt
    try:
        with open("PROMPT/system_prompt.md", "r") as f:
            system_prompt_content = f.read()
    except FileNotFoundError:
        print("Error: system_prompt.md not found.")
        return

    # 2. Load the input JSON data
    try:
        with open(input_file_path, "r") as f:
            input_json_content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{input_file_path}' was not found.")
        return

    # 3. THE RETRY LOOP
    user_message = f"Here is the input data:\n{input_json_content}"
    
    for attempt in range(1, MAX_JSON_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_JSON_RETRIES} ---")
        
        # Create a fresh agent/runner for every attempt to ensure clean context
        agent = create_search_agent(system_prompt_content)
        runner = InMemoryRunner(agent=agent)

        try:
            # Run the agent
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

            # Clean the output
            cleaned_json_string = clean_json_text(raw_text)
            
            # VALIDATION STEP: Try to parse
            json_obj = json.loads(cleaned_json_string)
            
            # IF WE REACH HERE, JSON IS VALID
            print("✅ Valid JSON received.")
            
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(json_obj, f, indent=2)
            print(f"✅ Successfully saved to {output_filename}")
            return  # Exit the function successfully

        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Parse Error on attempt {attempt}: {e}")
            print("   Retrying agent execution...")
            # Optional: Add a small sleep to prevent hammering if it's a transient issue
            time.sleep(2)
            continue # Loop to next attempt
        
        except Exception as e:
            print(f"❌ Unexpected Error on attempt {attempt}: {e}")
            return

    # If loop finishes without returning
    print("\n❌ Failed to generate valid JSON after max retries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a well log JSON file with ADK.")
    parser.add_argument("input_file", help="Path to the input JSON file")
    args = parser.parse_args()

    asyncio.run(main(args.input_file))