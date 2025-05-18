import requests
import json
import os
import sys
import traceback # For more detailed error printing
from datetime import datetime, timedelta, timezone # Ensure timezone for ISO format

# --- Configuration ---
GITHUB_USERNAME = "sfedor2020"  # Your GitHub username
OUTPUT_FILENAME = "stats.json"
# Ensures the script writes to the root of the repository when run by GitHub Actions
OUTPUT_FILE_PATH = os.path.join(os.getenv('GITHUB_WORKSPACE', os.getcwd()), OUTPUT_FILENAME)

# --- Securely Get GitHub Token ---
GITHUB_TOKEN = os.environ.get('GH_PAT')

headers = {
    "Authorization": f"bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json"
}

if not GITHUB_TOKEN:
    print("CRITICAL ERROR: GH_PAT secret not found. This script requires an authenticated PAT for reliable GraphQL API access.", file=sys.stderr)
    print("Please ensure GH_PAT is set as a secret in your GitHub Actions workflow.", file=sys.stderr)
    sys.exit(1)

def get_contributions_for_period(username, from_date_iso_utc, to_date_iso_utc):
    """
    Helper function to get contributions for a specific period (max 1 year).
    Dates must be full ISO 8601 UTC datetime strings.
    """
    query = """
    query($userName: String!, $fromDate: DateTime!, $toDate: DateTime!) {
      user(login: $userName) {
        contributionsCollection(from: $fromDate, to: $toDate) {
          contributionCalendar {
            totalContributions
          }
        }
      }
    }
    """
    variables = {
        "userName": username,
        "fromDate": from_date_iso_utc,
        "toDate": to_date_iso_utc
    }
    print(f"Querying contributions from {from_date_iso_utc} to {to_date_iso_utc}...")
    try:
        response = requests.post("https://api.github.com/graphql", headers=headers, json={"query": query, "variables": variables}, timeout=45) # Increased timeout slightly
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL error for period {from_date_iso_utc}-{to_date_iso_utc}: {data['errors']}", file=sys.stderr)
            return 0 # Return 0 if there's an error for this specific period
        contrib_data = data.get("data", {}).get("user", {}).get("contributionsCollection", {}).get("contributionCalendar", {})
        return contrib_data.get("totalContributions", 0)
    except requests.exceptions.Timeout:
        print(f"Timeout fetching contributions for {from_date_iso_utc}-{to_date_iso_utc}", file=sys.stderr)
        return 0
    except requests.exceptions.RequestException as e: # Catch other request-related errors
        print(f"RequestException fetching contributions for {from_date_iso_utc}-{to_date_iso_utc}: {e}", file=sys.stderr)
        return 0
    except Exception as e: # Catch any other unexpected error during this specific call
        print(f"Unexpected error in get_contributions_for_period ({from_date_iso_utc}-{to_date_iso_utc}): {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 0


def fetch_github_graphql_data():
    stats = {
        "username": GITHUB_USERNAME,
        "totalContributionsAllTime": 0,
        "totalContributionsLastYear": 0, # For last 365 days
        "totalRepositories": 0,
        "publicRepositories": 0,
        "privateRepositories": 0,
        "followers": 0,
        "following": 0,
        "totalStarsReceived": 0,
        "dataFetchedAt": datetime.now(timezone.utc).isoformat(), # Ensure UTC and use full ISO
        "errorFetching": None 
    }
    print(f"Script started at {stats['dataFetchedAt']} for user: {GITHUB_USERNAME}")

    try:
        # --- Get User Creation Date (createdAt) ---
        print("\nStep 1: Fetching user creation date...")
        user_creation_query = {
            "query": "query($userName: String!) { user(login: $userName) { createdAt } }",
            "variables": {"userName": GITHUB_USERNAME}
        }
        response_creation_date = requests.post("https://api.github.com/graphql", headers=headers, json=user_creation_query, timeout=30)
        response_creation_date.raise_for_status()
        creation_data_json = response_creation_date.json()
        
        created_at_str = "2008-02-08T00:00:00Z" # GitHub's approximate launch, very safe fallback
        if "errors" in creation_data_json:
            stats["errorFetching"] = f"GraphQL ERR (createdAt): {creation_data_json['errors']}"
            print(stats["errorFetching"], file=sys.stderr)
        else:
            user_creation_info = creation_data_json.get("data", {}).get("user", {})
            if user_creation_info and user_creation_info.get("createdAt"):
                created_at_str = user_creation_info["createdAt"]
                print(f"User createdAt: {created_at_str}")
            else:
                stats["errorFetching"] = "WARN: Could not parse createdAt. Using fallback for all-time contributions start."
                print(stats["errorFetching"], file=sys.stderr)
        
        # Ensure created_at_date is timezone-aware (UTC) for correct calculations
        created_at_date = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        current_utc_datetime = datetime.now(timezone.utc)
        current_year = current_utc_datetime.year
        created_year = created_at_date.year
        
        # --- Calculate All-Time Contributions by iterating through years ---
        print("\nStep 2: Calculating All-Time Contributions by year...")
        all_time_contributions_sum = 0
        for year_num in range(created_year, current_year + 1):
            # Define start and end of the year in UTC
            year_start_dt = datetime(year_num, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            year_end_dt = datetime(year_num, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

            # Adjust for the first year (use actual createdAt if it's not Jan 1)
            period_from_dt = max(year_start_dt, created_at_date)
            
            # Adjust for the current year (use current datetime if it's not Dec 31)
            period_to_dt = min(year_end_dt, current_utc_datetime)
            
            # Ensure 'from' is not after 'to', can happen for future iteration on Jan 1st.
            if period_from_dt >= period_to_dt: 
                print(f"Skipping year {year_num} as period_from ({period_from_dt}) is not before period_to ({period_to_dt}).")
                continue

            yearly_contribs = get_contributions_for_period(GITHUB_USERNAME, period_from_dt.isoformat(), period_to_dt.isoformat())
            print(f"Contributions in {year_num} (from {period_from_dt.date()} to {period_to_dt.date()}): {yearly_contribs}")
            all_time_contributions_sum += yearly_contribs
            # import time; time.sleep(0.1) # Optional small delay

        stats["totalContributionsAllTime"] = all_time_contributions_sum
        print(f"Total All-Time Contributions calculated: {stats['totalContributionsAllTime']}")

        # --- Calculate Last 365 Days Contributions ---
        print("\nStep 3: Calculating Last 365 Days Contributions...")
        one_year_ago_utc = current_utc_datetime - timedelta(days=365)
        # Ensure 'from' is not after 'to' (e.g. for very new accounts)
        if one_year_ago_utc < created_at_date :
            last_365_from_date_iso = created_at_date.isoformat()
        else:
            last_365_from_date_iso = one_year_ago_utc.isoformat()
        
        last_365_to_date_iso = current_utc_datetime.isoformat()
        
        if datetime.fromisoformat(last_365_from_date_iso) < datetime.fromisoformat(last_365_to_date_iso):
             stats["totalContributionsLastYear"] = get_contributions_for_period(GITHUB_USERNAME, last_365_from_date_iso, last_365_to_date_iso)
        else:
            stats["totalContributionsLastYear"] = 0 # if account is <1 day old or from_date is not before to_date
        print(f"Total Last 365 Days Contributions: {stats['totalContributionsLastYear']}")

        # --- Fetch Repos, Followers, Following ---
        print("\nStep 4: Fetching Repositories, Followers, Following...")
        other_stats_query_body = """
        query($userName: String!) {
          user(login: $userName) {
            repositories(first: 100, ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}, privacy: PUBLIC) {
              publicRepoCount: totalCount
              nodes { publicStars:stargazerCount }
            }
            allRepositories: repositories(first: 1, ownerAffiliations: OWNER) { # Just to get total count of all repos
                totalRepoCount: totalCount
            }
            followers { totalCount }
            following { totalCount }
          }
        }
        """
        other_stats_query = {"query": other_stats_query_body, "variables": {"userName": GITHUB_USERNAME}}
        response_other_stats = requests.post("https://api.github.com/graphql", headers=headers, json=other_stats_query, timeout=60)
        response_other_stats.raise_for_status()
        other_stats_json = response_other_stats.json()

        if "errors" in other_stats_json:
            error_msg_other = f"GraphQL ERR (other_stats): {other_stats_json['errors']}"
            print(error_msg_other, file=sys.stderr)
            if not stats["errorFetching"]: stats["errorFetching"] = error_msg_other
        
        user_data_other = other_stats_json.get("data", {}).get("user", {})
        if user_data_other:
            public_repo_data = user_data_other.get("repositories") # This is now specifically public repos
            if public_repo_data:
                stats["publicRepositories"] = public_repo_data.get("publicRepoCount", 0)
                # Sum stars only from public repos fetched (up to 100)
                stats["totalStarsReceived"] = sum(repo.get("publicStars", 0) for repo in public_repo_data.get("nodes", []))
            else: print("WARN: Public repositories data missing.", file=sys.stderr)
            
            all_repo_data = user_data_other.get("allRepositories")
            if all_repo_data:
                stats["totalRepositories"] = all_repo_data.get("totalRepoCount", 0)
            else: print("WARN: Total repositories count missing.", file=sys.stderr)

            # Derive private repositories
            if stats["totalRepositories"] >= stats["publicRepositories"]:
                stats["privateRepositories"] = stats["totalRepositories"] - stats["publicRepositories"]
            else: # Should not happen if data is consistent
                stats["privateRepositories"] = 0 
                print("WARN: Total repositories is less than public repositories. Setting private to 0.", file=sys.stderr)


            if user_data_other.get("followers"): stats["followers"] = user_data_other["followers"].get("totalCount", 0)
            else: print("WARN: Followers data missing.", file=sys.stderr)
            
            if user_data_other.get("following"): stats["following"] = user_data_other["following"].get("totalCount", 0)
            else: print("WARN: Following data missing.", file=sys.stderr)
        else:
            warn_msg = "WARN: 'user' data key missing for other stats."
            print(warn_msg, file=sys.stderr)
            if not stats["errorFetching"]: stats["errorFetching"] = warn_msg
            if "errors" not in other_stats_json: print(f"GraphQL other_stats_json (first 500): {str(other_stats_json)[:500]}", file=sys.stderr)

    except requests.exceptions.HTTPError as http_err:
        error_text = http_err.response.text[:500] if hasattr(http_err.response, 'text') else "No response text"
        stats["errorFetching"] = f"HTTP error: {http_err} - Response: {error_text}"
        print(stats["errorFetching"], file=sys.stderr)
    except requests.exceptions.RequestException as req_err: # Other requests errors like connection, timeout
        stats["errorFetching"] = f"Network Error: {req_err}"
        print(stats["errorFetching"], file=sys.stderr)
    except Exception as e: # Catch any other unexpected error
        stats["errorFetching"] = f"Unexpected error: {e}"
        print(stats["errorFetching"], file=sys.stderr)
        traceback.print_exc(file=sys.stderr) # Print full traceback for unexpected errors
    
    return stats

def save_stats_to_json(stats_data, filepath):
    """Saves the statistics to a JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(stats_data, f, indent=4)
        print(f"\nSuccessfully updated stats at {filepath}")
        print(f"Final data written: {json.dumps(stats_data)}") # Print the data that was actually written
    except IOError as e:
        print(f"\nError writing JSON file to {filepath}: {e}", file=sys.stderr)
        sys.exit(1) # Critical error if we can't write the file

if __name__ == "__main__":
    print(f"--- Starting GitHub Stats Update Script for {GITHUB_USERNAME} ---")
    github_stats_data = fetch_github_graphql_data()
    
    if github_stats_data.get("errorFetching"):
        print(f"\n--- ERRORS RECORDED DURING DATA FETCHING ---", file=sys.stderr)
        print(f"Error details: {github_stats_data['errorFetching']}", file=sys.stderr)
        print(f"Stats data might be incomplete or contain default values (zeros).", file=sys.stderr)
        print(f"--- END OF ERROR REPORT ---", file=sys.stderr)
    else:
        print("\n--- Data fetching appears to have completed without recorded errors. ---")

    save_stats_to_json(github_stats_data, OUTPUT_FILE_PATH)
    print(f"\n--- GitHub Stats Update Script Finished at {datetime.now(timezone.utc).isoformat()} ---")