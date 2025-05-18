import requests
import json
import os
import sys
from datetime import datetime, timedelta

# --- Configuration ---
GITHUB_USERNAME = "sfedor2020"  # Your GitHub username
OUTPUT_FILENAME = "stats.json"
OUTPUT_FILE_PATH = os.path.join(os.getcwd(), OUTPUT_FILENAME)

# --- Securely Get GitHub Token ---
GITHUB_TOKEN = os.environ.get('GH_PAT')

headers = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"bearer {GITHUB_TOKEN}"
}

if not GITHUB_TOKEN:
    print("CRITICAL ERROR: GH_PAT secret not found. This script requires an authenticated PAT.", file=sys.stderr)
    sys.exit(1)

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
        "dataFetchedAt": datetime.utcnow().isoformat() + "Z"
    }

    today_utc = datetime.utcnow()
    one_year_ago_utc = today_utc - timedelta(days=365)
    
    to_date_iso = today_utc.isoformat() + "Z"
    last_year_from_date_iso = one_year_ago_utc.isoformat() + "Z"
    all_time_from_date_iso = "" # Will be set from user's createdAt

    # Step 1: Get user's creation date
    user_creation_query_body = """
    query($userName: String!) {
      user(login: $userName) {
        createdAt
      }
    }
    """
    user_creation_query = {
        "query": user_creation_query_body,
        "variables": {"userName": GITHUB_USERNAME}
    }

    try:
        response_creation_date = requests.post("https://api.github.com/graphql", headers=headers, json=user_creation_query)
        response_creation_date.raise_for_status()
        creation_data_json = response_creation_date.json()

        if "errors" in creation_data_json:
            print(f"GraphQL query errors (fetching createdAt): {creation_data_json['errors']}", file=sys.stderr)
            sys.exit(1)

        user_creation_info = creation_data_json.get("data", {}).get("user", {})
        if user_creation_info and user_creation_info.get("createdAt"):
            all_time_from_date_iso = user_creation_info["createdAt"]
            print(f"User {GITHUB_USERNAME} created at: {all_time_from_date_iso}. Using this as start date for all-time contributions.")
        else:
            print(f"Could not fetch user creation date. Exiting.", file=sys.stderr)
            sys.exit(1)

        # Step 2: Get all other stats including both contribution periods
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
        
        response_main_data = requests.post("https://api.github.com/graphql", headers=headers, json=main_graphql_query)
        response_main_data.raise_for_status()
        main_data_json = response_main_data.json()

        if "errors" in main_data_json:
            print(f"GraphQL query errors (fetching main data): {main_data_json['errors']}", file=sys.stderr)
        
        user_data = main_data_json.get("data", {}).get("user", {})

        if user_data:
            all_time_contrib_data = user_data.get("allTimeContributions", {}).get("contributionCalendar", {})
            if all_time_contrib_data:
                stats["totalContributionsAllTime"] = all_time_contrib_data.get("totalContributions", 0)

            last_year_contrib_data = user_data.get("lastYearContributions", {}).get("contributionCalendar", {})
            if last_year_contrib_data:
                stats["totalContributionsLastYear"] = last_year_contrib_data.get("totalContributions", 0)

            repo_data = user_data.get("repositories", {})
            if repo_data:
                stats["totalRepositories"] = repo_data.get("totalCount", 0)
                current_repos = repo_data.get("nodes", [])
                total_stars = sum(repo.get("stargazerCount", 0) for repo in current_repos)
                public_repo_count = sum(1 for repo in current_repos if not repo.get("isPrivate"))
                
                stats["publicRepositories"] = public_repo_count
                stats["privateRepositories"] = stats["totalRepositories"] - public_repo_count
                stats["totalStarsReceived"] = total_stars

            if user_data.get("followers"):
                stats["followers"] = user_data.get("followers").get("totalCount", 0)
            if user_data.get("following"):
                stats["following"] = user_data.get("following").get("totalCount", 0)
        else:
            print("User data not found in main GraphQL response.", file=sys.stderr)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching GitHub GraphQL data: {e}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from GraphQL response: {e}", file=sys.stderr)
        if hasattr(e, 'doc') and e.doc:
             print(f"Problematic JSON text (first 500 chars): {e.doc[:500]}...", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)


    return stats

def save_stats_to_json(stats_data, filepath):
    """Saves the statistics to a JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(stats_data, f, indent=4)
        print(f"Successfully updated stats at {filepath}")
        print(f"Data: {json.dumps(stats_data)}")
    except IOError as e:
        print(f"Error writing JSON file to {filepath}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print(f"Running script to update GitHub stats for user: {GITHUB_USERNAME} using GraphQL (All-Time & Last Year Contributions)")
    
    github_stats_data = fetch_github_graphql_data()
    save_stats_to_json(github_stats_data, OUTPUT_FILE_PATH)
    
    print("Script finished.")