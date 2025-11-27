"""
Web search tool wrapping your existing searchTool.py functionality.
"""

import sys
import os
import requests
import json
from dotenv import load_dotenv

# Add parent directory to path to find searchTool.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


def search_with_serper(query: str) -> dict:
    """
    Search using Serper API.
    
    Args:
        query: Search query string
        
    Returns:
        Dictionary with search results or None on failure
    """
    api_key = os.getenv("SERPER_API_KEY")
    
    if not api_key:
        return None
    
    url = "https://google.serper.dev/search"
    
    payload = json.dumps({
        "q": query
    })
    
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Search error: {e}")
        return None


def search_well_logging_info_tool(query: str, max_results: int = 5) -> dict:
    """
    Search for well logging information using web search.
    
    This tool performs web searches specifically tailored for well logging,
    petrophysics, and oil and gas industry information.
    
    Args:
        query: Search query string focused on well logging topics
        max_results: Maximum number of search results to return (1-10)
    
    Returns:
        Dictionary with search results containing status, results list,
        query, and result_count, or error details if search failed.
    
    Example:
        >>> result = search_well_logging_info_tool("gamma ray log")
        >>> if result["status"] == "success":
        ...     for item in result["results"]:
        ...         print(item['title'])
    """
    try:
        # Use the search function
        results = search_with_serper(query)
        
        if results is None:
            return {
                "status": "error",
                "error_message": "Search failed - check SERPER_API_KEY in .env file",
                "query": query
            }
        
        # Format results
        formatted_results = []
        organic_results = results.get('organic', [])
        
        for idx, result in enumerate(organic_results[:max_results]):
            formatted_results.append({
                "title": result.get('title', 'No title'),
                "snippet": result.get('snippet', 'No description'),
                "url": result.get('link', ''),
                "position": idx + 1
            })
        
        return {
            "status": "success",
            "results": formatted_results,
            "query": query,
            "result_count": len(formatted_results)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Search failed: {str(e)}",
            "query": query
        }
