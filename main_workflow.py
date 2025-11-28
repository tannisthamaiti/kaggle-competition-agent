# main_workflow.py
import asyncio
import os
import traceback
import uuid

# Import the specific functions from your agents
from lastowellboreAgent import process_las_file
from searchAgent import main as search_main
from mergeAgent import main as merge_main

async def run_assembly_line():
    # --- Configuration ---
    LAS_FILE = os.path.abspath("test_data\\7_1-1.las")
    CONFIG_FILE = os.path.abspath("test_data\\sample_config.json")
    WELL_ID = "well-5555" # Unique ID for this run

    # Generate Traceable Session IDs
    run_uid = str(uuid.uuid4())[:8]
    session_step1 = f"{WELL_ID}-{run_uid}-step1-ingest"
    session_step2 = f"{WELL_ID}-{run_uid}-step2-search"
    session_step3 = f"{WELL_ID}-{run_uid}-step3-merge"

    print(f"=== 🚀 STARTING ASSEMBLY LINE (Run: {run_uid}) ===")

    # --- STEP 1: Run the Producer (LAS to JSON) ---
    print(f"\n--- Step 1: Processing LAS file {WELL_ID} (Session: {session_step1}) ---")
    generated_json_path = ""
    generated_json_path = await process_las_file(LAS_FILE, CONFIG_FILE, WELL_ID, session_step1)
    print(generated_json_path)

    # Check if Step 1 was successful
    if generated_json_path:
        print(f"✅ Step 1 Complete. Handoff file: {generated_json_path}")
        
        # --- STEP 2: Run the Consumer (JSON + Search) ---
        print(f"\n--- Step 2: Enriching data via Google Search (Session: {session_step2}) ---")
        await search_main(generated_json_path, session_step2)
        
        print("\n=== 🎉 STEP 2 FINISHED ===")
    else:
        print("\n❌ Workflow halted: Step 1 failed to produce a valid file.")
        return # Added return to stop execution if step 1 fails

    master_file = "masterLogs.json"
    child_file = "childLogs.json"
    
    print(f"\n--- Step 3: Merging Data (Session: {session_step3}) ---")
    try:
        # Attempt to execute the main async function
        await merge_main(master_file, child_file, session_step3)

    except FileNotFoundError as e:
        print(f"❌ Error: File not found. Please check the paths. Details: {e}")

    except PermissionError as e:
        print(f"❌ Error: Permission denied accessing the files. Details: {e}")

    except Exception as e:
        print(f"❌ An critical error occurred in merge_main: {e}")
        print("--- Stack Trace ---")
        traceback.print_exc()
        print("-------------------")


if __name__ == "__main__":
    asyncio.run(run_assembly_line())