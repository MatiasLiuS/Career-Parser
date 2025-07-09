# main.py
# This is the main entry point for the Jira-Driven Job Scraper.
# It orchestrates the entire workflow by calling functions from the other modules.

import os
import json
import asyncio
import datetime  # Import the datetime module
from dotenv import load_dotenv
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager




# --- Step 1: Load Environment Variables ---
# This MUST be the first step to ensure all API keys and configurations
# are available before other modules are imported.
load_dotenv()

# --- Step 2: Import Custom Modules ---
# These modules contain the specialized logic for Jira and Scraping.
# They are imported after load_dotenv() so they can access the environment variables.
import jira_manager
import scraper


def save_results_to_json(results, filename="results.json"):
    """Saves the final list of found jobs to a JSON file for review."""
    print(f"\n--- Saving {len(results)} found jobs to {filename} ---")
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4)
        print(f"✅ Successfully saved results to {filename}")
    except Exception as e:
        print(f"❌ Failed to save results to JSON file: {e}")

def log_message(message):
    """Prints a message with a timestamp."""
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

async def main():
    """The main asynchronous function that controls the script's execution flow."""
    log_message("--- Starting Jira-Driven Job Scraper ---")
    
    # --- Step 3: Connect to Jira ---
    jira_client = jira_manager.connect_to_jira()
    if not jira_client:
        return # Stop if the connection fails

    # --- Step 4: Get Scraping Tasks from Jira ---
    targets, issue_map = jira_manager.get_requests_from_jira(jira_client)
    if not targets:
        log_message("No new requests found in Jira. Exiting.")
        return
    
    # --- Step 5: Initialize a Single, Persistent Browser Session ---
    # This is more stable and efficient than creating a new browser for every request.
    log_message("-> Initializing persistent browser session...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # Use modern headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3") # Suppress console noise
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    log_message("-> Browser session initialized.")
    
    all_found_jobs = []
    # The try...finally block ensures the browser is always closed, even if an error occurs.
    try:
        # --- Step 6: Loop Through Each Company Task ---
        for company in targets:
            # Pass the persistent driver to the scraper for it to use
            company_results = await scraper.process_company(driver, company)
            all_found_jobs.extend(company_results)
            
            # # --- Step 7: Update the Original Jira Request Ticket ---
            # company_name = company['company_name']
            # if company_name in issue_map:
            #     issue_key_to_update = issue_map[company_name]
            #     log_message(f"Processing complete for {company_name}. Updating Jira ticket {issue_key_to_update}.")
            #     jira_manager.transition_jira_issue(jira_client, issue_key_to_update, "Done")
    finally:
        # --- Step 8: Close the Browser Session ---
        log_message("-> Closing persistent browser session.")
        driver.quit()


    # --- Step 9: Process the Results ---
    if all_found_jobs:
        # Save results to a local file for debugging and review
        save_results_to_json(all_found_jobs)
        
        # Loop through the found jobs and create or update tickets in Jira
        log_message(f"--- Found {len(all_found_jobs)} total jobs. Creating/Updating tickets in '{jira_manager.JIRA_OUTPUT_PROJECT_KEY}' project. ---")
        
        # 1. Create a list of all the async tasks to be run
        tasks = [jira_manager.create_output_ticket_async(jira_client, job_card) for job_card in all_found_jobs]
        
        # 2. Run all tasks concurrently and wait for them to complete
        await asyncio.gather(*tasks)

    
    # --- Step 10: Print Final Summary ---
    log_message("--- Request Summary ---")
    print(f"Total Selenium page loads: {scraper.SELENIUM_PAGE_LOADS}")
    print(f"Jira Tickets Created: {jira_manager.CREATED_TICKETS}")
    print(f"Jira Tickets Updated: {jira_manager.UPDATED_TICKETS}")
            
    log_message("--- Full workflow complete. ---")

# --- Step 0: Script Entry Point ---
if __name__ == "__main__":
    try:
        # Run the main asynchronous function
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle the user pressing Ctrl+C gracefully
        print("\n\n--- Script interrupted by user. Exiting. ---")
