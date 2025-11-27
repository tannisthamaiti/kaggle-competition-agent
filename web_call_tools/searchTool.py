import requests
from dotenv import load_dotenv
#from tavily import TavilyClient
#import wikipedia
import os
import json

## serper password 9F.9cdBR5PekyUc

load_dotenv() # <-- ADDED THIS

def tavily_search_tool(query: str, max_results: int = 5, include_images: bool = False) -> list[dict]:
    """
    Perform a search using the Tavily API.

    Args:
        query (str): The search query.
        max_results (int): Number of results to return (default 5).
        include_images (bool): Whether to include image results.

    Returns:
        list[dict]: A list of dictionaries with keys like 'title', 'content', and 'url'.
    """
    params = {}
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found in environment variables.")
    params['api_key'] = api_key

    #client = TavilyClient(api_key)

    api_base_url = os.getenv("DLAI_TAVILY_BASE_URL")
    if api_base_url:
        params['api_base_url'] = api_base_url

    client = TavilyClient(api_key=api_key, api_base_url=api_base_url)

    try:
        response = client.search(
            query=query,
            max_results=max_results,
            include_images=include_images
        )

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", "")
            })

        if include_images:
            for img_url in response.get("images", []):
                results.append({"image_url": img_url})

        return results

    except Exception as e:
        return [{"error": str(e)}]  # For LLM-friendly agents
    

def search_with_serper(query):
    """
    Performs a web search using the Serper API.
    
    Args:
        query (str): The search query.
        
    Returns:
        dict: The search results from the API, or None if an error occurs.
    """
    
    # 1. Get the API key from an environment variable
    # It's best practice to not hardcode keys in your script.
    api_key = os.getenv("SERPER_API_KEY")
    
    if not api_key:
        print("Error: SERPER_API_KEY environment variable not set.")
        print("Please get your API key from https://serper.dev and set the environment variable.")
        return None
        
    # 2. Define the API endpoint and headers
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    # 3. Create the payload with the query
    payload = json.dumps({
        "q": query
    })
    
    # 4. Make the POST request
    try:
        response = requests.post(url, headers=headers, data=payload)
        
        # Check if the request was successful
        response.raise_for_status() 
        
        # 5. Parse and return the JSON response
        return response.json()
        
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred during the request: {req_err}")
    except json.JSONDecodeError:
        print("Error: Failed to decode the JSON response from the server.")
    
    return None




# if __name__ == "__main__":
#     # --- Simple Test for the function ---
    
#     test_query = "what is a gamma ray log in well logging"
    
#     print(f"--- Testing search_with_serper function with query: '{test_query}' ---")
    
#     results = search_with_serper(test_query)
    
#     if results:
#         print("\nSuccessfully received results from Serper API.")
#         # Pretty-print the full JSON response to inspect it
#         print(json.dumps(results, indent=2))
        
#         # You can also check a specific part, like the first organic result
#         organic_results = results.get('organic', [])
#         if organic_results:
#             print(f"\n--- Snippet of first result ---")
#             print(organic_results[0].get('snippet', 'No snippet available.'))
#             print(f"---------------------------------")
#         else:
#             print("\nNo organic results found for this query.")
            
#     else:
#         print("\nTest failed: Did not receive results. Check API key and network.")
        
#     print(f"--- Test complete ---")