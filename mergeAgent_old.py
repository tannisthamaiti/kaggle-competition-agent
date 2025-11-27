import os
import json
from dotenv import load_dotenv
import google.generativeai as genai
from google.ai.generativelanguage import Part
import re

# --- 1. Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

genai.configure(api_key=GEMINI_API_KEY)

MASTER_FILE = 'masterLogs.json'
CHILD_FILE = 'childLogs.json'
SYSTEM_PROMPT_FILE = 'merge_system_prompt.md'
OUTPUT_FILE = 'merged_logs.json'

# --- 2. Helper Functions ---

def load_json_file(filename, is_list=True):
    """Loads a JSON file with error handling."""
    print(f"Loading {filename}...")
    if not os.path.exists(filename):
        print(f"Error: File not found: {filename}")
        return None
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
            # Clean potential markdown wrappers like ```json ... ```
            match = re.search(r'```json\s*([\s\S]+?)\s*```', raw_text)
            if match:
                json_text = match.group(1)
            # Find the first { or [ to the last } or ]
            elif raw_text.strip().startswith('`'):
                 start = raw_text.find('[') if is_list else raw_text.find('{')
                 end = raw_text.rfind(']') if is_list else raw_text.rfind('}')
                 if start != -1 and end != -1:
                     json_text = raw_text[start:end+1]
                 else:
                     json_text = raw_text
            else:
                 json_text = raw_text

            data = json.loads(json_text)
            return data
            
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from {filename}. Text was: {json_text[:200]}...")
        return None
    except Exception as e:
        print(f"An unexpected error occurred loading {filename}: {e}")
        return None

def clean_model_response(raw_text):
    """
    Extracts the pure JSON string from the model's text response,
    removing markdown fences (```json) and other text.
    """
    # Use regex to find the content between ```json and ```
    match = re.search(r'```json\s*([\s\S]+?)\s*```', raw_text)
    if match:
        return match.group(1).strip()
    
    # Fallback: Find the first '[' or '{' to the last ']' or '}'
    start_bracket = raw_text.find('[')
    start_brace = raw_text.find('{')
    
    if start_bracket == -1 and start_brace == -1:
        raise ValueError("No JSON list or object found in response.")

    if start_bracket == -1:
        start_index = start_brace
    elif start_brace == -1:
        start_index = start_bracket
    else:
        start_index = min(start_bracket, start_brace)
        
    end_bracket = raw_text.rfind(']')
    end_brace = raw_text.rfind('}')
    end_index = max(end_bracket, end_brace)
    
    if start_index != -1 and end_index != -1:
        return raw_text[start_index:end_index+1].strip()
        
    raise ValueError("Valid JSON content could not be extracted.")


# --- 3. Agent Runner ---

def run_agent(model, prompt_data):
    """
    Sends the combined data to the model and saves the final JSON response.
    """
    print(f"\nSending data to Gemini for intelligent merging...")
    
    # Start a chat session (to respect system_instruction)
    chat = model.start_chat()
    
    # Send the combined JSON data as the first message
    response = chat.send_message(json.dumps(prompt_data))
    
    try:
        # Get the model's response part
        part = response.candidates[0].content.parts[0]
        
        if part.text:
            raw_response_text = part.text
            print(f"Gemini (Raw Response): Received {len(raw_response_text)} bytes of data.")
            
            # Save the raw text response to the output file
            try:
                # --- FIX: Clean the response before parsing ---
                cleaned_json_text = clean_model_response(raw_response_text)
                
                # Basic validation: is it valid JSON?
                json.loads(cleaned_json_text)
                
                # Write the *cleaned* JSON to the file
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write(cleaned_json_text)
                print(f"\nSuccessfully cleaned, validated, and saved merged list to {OUTPUT_FILE}")
                
                # Optional: Pretty-print the first 3 items for verification
                final_data = json.loads(cleaned_json_text)
                print("\n--- Merge Verification (First 3 Logs) ---")
                print(json.dumps(final_data[:3], indent=2))
                print("-------------------------------------------")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"\n--- ERROR: COULD NOT PARSE VALID JSON FROM MODEL ---")
                print(f"Error Details: {e}")
                print("Gemini (Raw Response):")
                print(raw_response_text)
                print("------------------------------------------------")
            except Exception as e:
                print(f"Error saving file: {e}")

        else:
            # Handle other cases (e.g., SAFETY, or empty response)
            print(f"Gemini (Stopped): Finish Reason: {response.candidates[0].finish_reason}")
            print(f"Full Response: {response.candidates[0].content}")

    except (AttributeError, IndexError, ValueError) as e:
        print(f"\nAn error occurred parsing the agent's response: {e}")
        print(f"Full Response Object (first 500 chars): {str(response)[:500]}...")
    
    except Exception as e:
        print(f"A critical error occurred: {e}")

# --- 4. Main Execution ---

if __name__ == "__main__":
    
    # 1. Load the system prompt from the file
    try:
        with open(SYSTEM_PROMPT_FILE, "r") as f:
            system_prompt_content = f.read()
        print(f"Loaded system prompt from {SYSTEM_PROMPT_FILE}")
    except FileNotFoundError:
        print(f"Error: {SYSTEM_PROMPT_FILE} not found. Please create it.")
        exit(1)

    # 2. Load the Master and Child JSON data
    master_logs = load_json_file(MASTER_FILE, is_list=True)
    if master_logs is None:
        exit(1)
        
    child_data = load_json_file(CHILD_FILE, is_list=False)
    if child_data is None:
        exit(1)

    # Extract the nested child list
    child_logs = child_data.get('enrichedCurves')
    if child_logs is None:
        print(f"Error: Could not find 'enrichedCurves' key in {CHILD_FILE}")
        exit(1)

    # 3. Construct the single JSON input for the model
    # This combines both files into one object, as defined in the new prompt
    combined_input = {
        "masterLogs": master_logs,
        "childLogs": child_logs
    }

    # 4. Initialize the model WITH the new system prompt
    # This agent does not need tools, just reasoning.
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt_content
    )
    
    # 5. Run the agent
    run_agent(model, combined_input)

