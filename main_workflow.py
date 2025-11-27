# main_workflow.py
import asyncio
import os
import traceback

# Import the specific functions from your agents
from lastowellboreAgent import process_las_file
from searchAgent import create_search_agent, main
import mergeAgent as ma

async def run_assembly_line():
    # --- Configuration ---
    LAS_FILE = os.path.abspath("test_data\\7_1-1.las")
    CONFIG_FILE = os.path.abspath("test_data\\sample_config.json")
    WELL_ID = "well-5555" # Unique ID for this run

    print("=== 🚀 STARTING ASSEMBLY LINE ===")

    # --- STEP 1: Run the Producer (LAS to JSON) ---
    print(f"\n--- Step 1: Processing LAS file {WELL_ID} ---")
    generated_json_path =""
    generated_json_path = await process_las_file(LAS_FILE, CONFIG_FILE, WELL_ID)
    print(generated_json_path)

    # Check if Step 1 was successful
    if generated_json_path:
        print(f"✅ Step 1 Complete. Handoff file: {generated_json_path}")
        
        # --- STEP 2: Run the Consumer (JSON + Search) ---
        print(f"\n--- Step 2: Enriching data via Google Search ---")
        #create_search_agent(generated_json_path)
        await main(generated_json_path)
        
        print("\n=== 🎉 STEP 2 FINISHED ===")
    else:
        print("\n❌ Workflow halted: Step 1 failed to produce a valid file.")
    master_file = "masterLogs.json"
    child_file = "childLogs.json"
    try:
    # Attempt to execute the main async function
        await ma.main(master_file, child_file)

    except FileNotFoundError as e:
    # Handles cases where master_file or child_file paths are incorrect
        print(f"❌ Error: File not found. Please check the paths. Details: {e}")

    except PermissionError as e:
    # Handles read/write permission issues
        print(f"❌ Error: Permission denied accessing the files. Details: {e}")

    except Exception as e:
    # Catches any other runtime errors (logic errors, type errors, etc.)
        print(f"❌ An critical error occurred in ma.main: {e}")
    
    # Prints the full stack trace so you can see exactly where it failed
        print("--- Stack Trace ---")
        traceback.print_exc()
        print("-------------------")


if __name__ == "__main__":
    
    asyncio.run(run_assembly_line())