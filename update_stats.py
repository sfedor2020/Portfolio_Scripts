import requests
import json
import os
import sys
import traceback # For more detailed error printing
from datetime import datetime, timedelta

# --- Configuration ---
GITHUB_USERNAME = "sfedor2020"  # Your GitHub username
OUTPUT_FILENAME = "stats.json"
# Ensures the script writes to the root of the repository when run by GitHub Actions
OUTPUT_FILE_PATH = os.path.join(os.getenv('GITHUB_WORKSPACE', os.getcwd()), OUTPUT_FILENAME)


# --- Securely Get GitHub Token ---
GITHUB_TOKEN = os.environ.get('GH_PAT')

headers = {
    "Accept": "application/vnd.github.v3+json", # Good practice, though GraphQL mainly uses application/json
    "Authorization": f"bearer {GITHUB_TOKEN}",  # Use 'bearer' for GraphQL
    "Content-Type": "application/json"          # For POST requests with JSON body
}

if not GITHUB_TOKEN:
    print("CRITICAL ERROR: GH_PAT secret not found. This script requires an authenticated PAT for reliable GraphQL API access.", file=sys.stderr)
    print("Please ensure GH_PAT is set as a secret in your GitHub Actions workflow.", file=sys.stderr)
    sys.exit(1) # Exit if no token, as GraphQL calls will fail or be severely limited.

def fetch_github_graphql_data():
    """Fetches required data from the GitHub GraphQL API."""
    stats = {
        "username": GITHUB_USERNAME,
        "totalContributionsAllTime": 0,
        "totalContributionsLastYear": 0,
        "totalRepositories": 0,
        "publicRepositories": 0,
        "privateRepositories": 0,
        "followers": 0,
        "following": 0,
        "totalStarsReceived": 0,
        "dataFetchedAt": datetime.utcnow().isoformat() + "Z",
        "errorFetching": None # To store any error message for debugging in stats.json
    }

    # Dates for GraphQL
    today_utc = datetime.utcnow()
    one_year_ago_utc = today_utc - timedelta(days=365)
    
    to_date_iso = today_utc.isoformat() + "Z"
    last_year_from_date_iso = one_year_ago_utc.isoformat() + "Z"
    all_time_from_date_iso = "2008-01-01T00:00:00Z" # Default fallback, will be updated

    print(f"Script started at {stats['dataFetchedAt']}")
    print(f"Fetching data for GitHub user: {GITHUB_USERNAME}")

    try:
        # Step 1: Get user's account creation date for "all time" contributions
        print("\nStep 1: Fetching user creation date...")
        user_creation_query_body = """
        query($userName: String!) {
          user(login: $userName) {
            createdAt
          }
        }
        """
        user_creation_query = {"query": user_creation_query_body, "variables": {"userName": GITHUB_USERNAME}}
        
        response_creation_date = requests.post("https://api.github.com/graphql", headers=headers, json=user_creation_query, timeout=30)
        response_creation_date.raise_for_status() # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
        creation_data_json = response_creation_date.json()

        if "errors" in creation_data_json:
            error_message = f"GraphQL ERR (createdAt): {creation_data_json['errors']}"
            print(error_message, file=sys.stderr)
            stats["errorFetching"] = error_message 
            # Allow fallback to default all_time_from_date_iso
        else:
            user_creation_info = creation_data_json.get("data", {}).get("user", {})
            if user_creation_info and user_creation_info.get("createdAt"):
                all_time_from_date_iso = user_creation_info["createdAt"]
                print(f"User {GITHUB_USERNAME} createdAt: {all_time_from_date_iso}. Using this as start date for all-time contributions.")
            else:
                warn_message = "WARN: Could not parse createdAt from GraphQL. Using fallback for all_time_from_date."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message
        
        print(f"Using fromDate (all-time): {all_time_from_date_iso}, fromDate (last-year): {last_year_from_date_iso}, toDate: {to_date_iso}")

        # Step 2: Get all other stats including both contribution periods
        print("\nStep 2: Fetching main data (contributions, repos, followers)...")
        main_graphql_query_body = """
        query($userName: String!, $allTimeFromDate: DateTime!, $lastYearFromDate: DateTime!, $toDate: DateTime!) {
          user(login: $userName) {
            allTimeContributions: contributionsCollection(from: $allTimeFromDate, to: $toDate) {
              contributionCalendar {
                totalContributions
              }
            }
            lastYearContributions: contributionsCollection(from: $lastYearFromDate, to: $toDate) {
              contributionCalendar {
                totalContributions
              }
            }
            repositories(first: 100, ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
              totalCount
              nodes {
                stargazerCount
                isPrivate
              }
            }
            followers {
              totalCount
            }
            following {
              totalCount
            }
          }
        }
        """
        main_graphql_query = {
            "query": main_graphql_query_body,
            "variables": {
                "userName": GITHUB_USERNAME,
                "allTimeFromDate": all_time_from_date_iso,
                "lastYearFromDate": last_year_from_date_iso,
                "toDate": to_date_iso
            }
        }
        
        response_main_data = requests.post("https://api.github.com/graphql", headers=headers, json=main_graphql_query, timeout=60) # Longer timeout for potentially larger query
        response_main_data.raise_for_status()
        main_data_json = response_main_data.json()

        if "errors" in main_data_json:
            error_message = f"GraphQL ERR (main data): {main_data_json['errors']}"
            print(error_message, file=sys.stderr)
            if not stats["errorFetching"]: stats["errorFetching"] = error_message # Store first error encountered
        
        user_data = main_data_json.get("data", {}).get("user")

        if user_data:
            print("Processing main data from GraphQL response...")
            # All-Time Contributions
            all_time_contrib_collection = user_data.get("allTimeContributions")
            if all_time_contrib_collection and all_time_contrib_collection.get("contributionCalendar"):
                stats["totalContributionsAllTime"] = all_time_contrib_collection["contributionCalendar"].get("totalContributions", 0)
            else:
                warn_message = "WARN: 'allTimeContributions.contributionCalendar' data missing or incomplete in GraphQL response."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message


            # Last Year Contributions
            last_year_contrib_collection = user_data.get("lastYearContributions")
            if last_year_contrib_collection and last_year_contrib_collection.get("contributionCalendar"):
                stats["totalContributionsLastYear"] = last_year_contrib_collection["contributionCalendar"].get("totalContributions", 0)
            else:
                warn_message = "WARN: 'lastYearContributions.contributionCalendar' data missing or incomplete in GraphQL response."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message

            # Repositories, Stars, Public/Private Count
            repo_data = user_data.get("repositories")
            if repo_data:
                stats["totalRepositories"] = repo_data.get("totalCount", 0)
                current_repos = repo_data.get("nodes", []) # Up to 100 repos
                total_stars = sum(repo.get("stargazerCount", 0) for repo in current_repos)
                public_repo_count = sum(1 for repo in current_repos if not repo.get("isPrivate"))
                
                stats["publicRepositories"] = public_repo_count
                # Derive private count. If totalRepositories is 0, privateRepositories should also be 0.
                stats["privateRepositories"] = stats["totalRepositories"] - public_repo_count if stats["totalRepositories"] > 0 else 0
                stats["totalStarsReceived"] = total_stars
            else:
                warn_message = "WARN: 'repositories' data missing in GraphQL response."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message


            # Followers & Following
            followers_data = user_data.get("followers")
            if followers_data:
                stats["followers"] = followers_data.get("totalCount", 0)
            else:
                warn_message = "WARN: 'followers' data missing in GraphQL response."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message

            following_data = user_data.get("following")
            if following_data:
                stats["following"] = following_data.get("totalCount", 0)
            else:
                warn_message = "WARN: 'following' data missing in GraphQL response."
                print(warn_message, file=sys.stderr)
                if not stats["errorFetching"]: stats["errorFetching"] = warn_message
        else: # user_data is None
            warn_message = "WARN: 'user' data key missing or null in main GraphQL response. Stats will be default (zeros)."
            print(warn_message, file=sys.stderr)
            if not stats["errorFetching"]: stats["errorFetching"] = warn_message
            if "errors" not in main_data_json: # If no specific GQL error, print response for inspection
                 print(f"GraphQL main_data_json (first 500 chars): {str(main_data_json)[:500]}", file=sys.stderr)


    except requests.exceptions.HTTPError as http_err:
        error_message = f"HTTP error occurred during GraphQL request: {http_err} - Response: {http_err.response.text[:500]}"
        print(error_message, file=sys.stderr)
        if not stats["errorFetching"]: stats["errorFetching"] = str(http_err)
    except requests.exceptions.RequestException as req_err: # Other requests errors like connection, timeout
        error_message = f"Network Error fetching GitHub GraphQL data: {req_err}"
        print(error_message, file=sys.stderr)
        if not stats["errorFetching"]: stats["errorFetching"] = str(req_err)
    except json.JSONDecodeError as json_err:
        error_message = f"JSON Decode Error from GraphQL response: {json_err}"
        print(error_message, file=sys.stderr)
        if hasattr(json_err, 'doc') and json_err.doc:
             print(f"Problematic JSON text (first 500 chars): {json_err.doc[:500]}...", file=sys.stderr)
        if not stats["errorFetching"]: stats["errorFetching"] = str(json_err)
    except Exception as e: # Catch any other unexpected error
        error_message = f"An unexpected error occurred in fetch_github_graphql_data: {e}"
        print(error_message, file=sys.stderr)
        traceback.print_exc(file=sys.stderr) # Print full traceback for unexpected errors
        if not stats["errorFetching"]: stats["errorFetching"] = str(e)

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
    
    # Check if any errors were recorded during fetching, and if so, print them prominently
    if github_stats_data.get("errorFetching"):
        print(f"\n--- ERRORS ENCOUNTERED DURING DATA FETCHING ---", file=sys.stderr)
        print(f"Error details: {github_stats_data['errorFetching']}", file=sys.stderr)
        print(f"Stats data might be incomplete or contain default values (zeros).", file=sys.stderr)
        print(f"--- END OF ERROR REPORT ---", file=sys.stderr)
    else:
        print("\n--- Data fetching completed without recorded errors. ---")


    save_stats_to_json(github_stats_data, OUTPUT_FILE_PATH)
    
    print(f"\n--- GitHub Stats Update Script Finished at {datetime.utcnow().isoformat() + 'Z'} ---")