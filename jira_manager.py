# jira_manager.py
# This module handles all interactions with the Jira API.

import os
from jira import JIRA

# --- Load Jira-specific environment variables ---
# Note: The main.py file will run load_dotenv() first.
JIRA_SERVER = os.getenv("JIRA_SERVER")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_REQUEST_PROJECT_KEY = os.getenv("JIRA_REQUEST_PROJECT_KEY") 
JIRA_OUTPUT_PROJECT_KEY = os.getenv("JIRA_OUTPUT_PROJECT_KEY")
JIRA_FIELD_COMPANY_NAME = os.getenv("JIRA_FIELD_COMPANY_NAME")
JIRA_FIELD_CAREERS_URL = os.getenv("JIRA_FIELD_CAREERS_URL")
JIRA_FIELD_KEYWORDS = os.getenv("JIRA_FIELD_KEYWORDS")

# --- Ticket Counters ---
CREATED_TICKETS = 0
UPDATED_TICKETS = 0

def connect_to_jira():
    """Establishes a connection to the Jira server."""
    try:
        print("Connecting to Jira..."); 
        jira_client = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN))
        print("✅ Successfully connected to Jira.")
        return jira_client
    except Exception as e:
        print(f"❌ Failed to connect to Jira: {e}")
        return None

def get_requests_from_jira(jira_client):
    """Fetches all 'To Do' scraping requests from the input project."""
    if not all([jira_client, JIRA_REQUEST_PROJECT_KEY, JIRA_FIELD_COMPANY_NAME, JIRA_FIELD_CAREERS_URL, JIRA_FIELD_KEYWORDS]):
        print("❌ Jira input client or custom field IDs not configured in .env file.")
        return [], {}
    
    jql_query = f'project = "{JIRA_REQUEST_PROJECT_KEY}" AND status = "To Do"'
    print(f"Searching for Jira requests with JQL: {jql_query}")
    try:
        issues = jira_client.search_issues(jql_query)
        print(f"Found {len(issues)} new scraping requests in Jira.")
        targets, issue_map = [], {}
        for issue in issues:
            try:
                company_name = getattr(issue.fields, JIRA_FIELD_COMPANY_NAME)
                careers_url = getattr(issue.fields, JIRA_FIELD_CAREERS_URL)
                keywords_str = getattr(issue.fields, JIRA_FIELD_KEYWORDS)
                if not all([company_name, careers_url, keywords_str]): 
                    continue
                keywords = [kw.strip() for kw in keywords_str.split(',')]
                targets.append({"company_name": company_name, "careers_url": careers_url, "keywords": keywords})
                issue_map[company_name] = issue.key
            except AttributeError: 
                continue
        return targets, issue_map
    except Exception as e:
        print(f"❌ Error fetching issues from Jira: {e}")
        return [], {}

def transition_jira_issue(jira_client, issue_key, transition_name):
    """Transitions a Jira issue to a new status (e.g., 'Done')."""
    try:
        jira_client.transition_issue(issue_key, transition=transition_name)
        print(f"✅ Transitioned ticket {issue_key} to '{transition_name}'.")
    except Exception as e:
        print(f"❌ Failed to transition ticket {issue_key}: {e}")

def find_existing_output_ticket(jira_client, job_id):
    """Checks if a ticket for a given job ID already exists in the output project."""
    if not job_id or job_id == "N/A": 
        return None
    
    # --- FIX: Using a more robust JQL query to find the job ID ---
    # This searches for the exact job ID string anywhere in the description.
    jql = f'project = "{JIRA_OUTPUT_PROJECT_KEY}" AND description ~ "{job_id}"'
    
    try:
        issues = jira_client.search_issues(jql, maxResults=1)
        return issues[0] if issues else None
    except Exception as e:
        print(f"  -> Error searching for existing output ticket: {e}")
        return None

def create_output_ticket(jira_client, job_card):
    """Creates a new ticket in the output project or updates an existing one."""
    global CREATED_TICKETS, UPDATED_TICKETS
    if not JIRA_OUTPUT_PROJECT_KEY:
        print("  -> ❌ JIRA_OUTPUT_PROJECT_KEY not set in .env. Cannot create ticket.")
        return
        
    summary = f"{job_card['Company']}: {job_card['Job Title']}"
    description = f"""
h2. Company
{job_card['Company']}

h2. Job Title
{job_card['Job Title']}

h2. Location
{job_card['Location']}

h2. Matched Keywords
{', '.join(job_card['Matched Keywords'])}

h2. Link to Job
{job_card['Link to Job']}

h3. Unique Job ID
{job_card['Unique Job ID']}
"""
    
    # --- FIX: Logic to update existing tickets instead of creating duplicates ---
    existing_ticket = find_existing_output_ticket(jira_client, job_card["Unique Job ID"])
    
    if existing_ticket:
        print(f"  -> Ticket {existing_ticket.key} already exists for Job ID {job_card['Unique Job ID']}. Updating it.")
        try:
            existing_ticket.update(fields={'summary': summary, 'description': description})
            print(f"  -> ✅ Successfully updated ticket: {existing_ticket.key}")
            UPDATED_TICKETS += 1
        except Exception as e:
            print(f"  -> ❌ Failed to update ticket {existing_ticket.key}: {e}")
        return

    # If no existing ticket is found, create a new one
    issue_dict = {
        'project': {'key': JIRA_OUTPUT_PROJECT_KEY},
        'summary': summary,
        'description': description,
        'issuetype': {'name': 'Task'}
    }
    try:
        new_issue = jira_client.create_issue(fields=issue_dict)
        print(f"  -> ✅ Successfully created output ticket: {new_issue.key}")
        CREATED_TICKETS += 1
    except Exception as e:
        print(f"  -> ❌ Failed to create output ticket for '{summary}': {e}")
