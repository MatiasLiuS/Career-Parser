# greenhouse_strategy.py
# This module contains the parsing strategy for Greenhouse job boards.

import re
import httpx
import json
from bs4 import BeautifulSoup

async def parse_strategy_greenhouse_api(soup, company):
    """
    Fetches all job details from a Greenhouse board using its JSON API.
    This is much faster and more reliable than using Selenium.
    """
    print("  -> Using Greenhouse API parsing strategy.")
    
    board_token = None
    
    # Method 1: Try to find the board token from the standard script tag.
    script_tag = soup.find('script', src=re.compile(r'boards.greenhouse.io/embed/job_board'))
    if script_tag and script_tag.get('src'):
        match = re.search(r'job_board\?for=([^&]+)', script_tag['src'])
        if match:
            board_token = match.group(1)
            print("    -> Found board token via script tag.")

    # Method 2: If the script isn't found, guess the token from the company name.
    if not board_token:
        print("    -> Script tag not found. Guessing board token from company name.")
        board_token = re.sub(r'[^a-z0-9]', '', company['company_name'].lower().strip())
        if not board_token:
            print("  -> ❌ Could not create a valid board token from the company name.")
            return []

    print(f"    -> Using board token: {board_token}")
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"    -> Querying API: {api_url}")
            response = await client.get(api_url, timeout=30)
            response.raise_for_status()
            api_data = response.json()
            
            all_job_details = []
            for job in api_data.get('jobs', []):
                job_content = job.get('content')
                # If content is missing, make a secondary request for full job details
                if not job_content and job.get('id'):
                    detail_api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job.get('id')}"
                    detail_response = await client.get(detail_api_url)
                    if detail_response.status_code == 200:
                        job_content = detail_response.json().get('content', '')
                
                description_soup = BeautifulSoup(job_content or '', 'html.parser')
                
                all_job_details.append({
                    "title": job.get('title', 'Title Not Found').strip(),
                    "location": job.get('location', {}).get('name', 'Location Not Found').strip(),
                    "link": job.get('absolute_url', '#').strip(),
                    "description": description_soup.get_text(" ", strip=True)
                })
            print(f"    -> Successfully fetched {len(all_job_details)} jobs from the API.")
            return all_job_details
        except httpx.HTTPStatusError as e:
            print(f"  -> ❌ Failed to fetch data from Greenhouse API. Status: {e.response.status_code}. URL: {api_url}")
            return []
        except httpx.RequestError as e:
            print(f"  -> ❌ Network error while fetching from Greenhouse API: {e}")
            return []
        except json.JSONDecodeError:
            print("  -> ❌ Failed to parse JSON response from Greenhouse API.")
            return []