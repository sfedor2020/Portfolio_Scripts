import requests
import json
import os
import sys
import traceback
from datetime import datetime, timedelta

# --- Configuration ---
GITHUB_USERNAME = "sfedor2020"
OUTPUT_FILENAME = "stats.json"
OUTPUT_FILE_PATH = os.path.join(os.getenv('GITHUB_WORKSPACE', os.getcwd()), OUTPUT_FILENAME)

# --- Securely Get GitHub Token ---
GITHUB_TOKEN = os.environ.get('GH_PAT')
headers = {
    "Authorization": f"bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json"
}

if not GITHUB_TOKEN:
    print("CRITICAL ERROR: GH_PAT secret not found.", file=sys.stderr)
    sys.exit(1)

def get_contributions_for_period(username, from_date_iso, to_date_iso):
    """Helper function to get contributions for a specific period (max 1 year)."""
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
        "fromDate": from_date_iso,
        "toDate": to_date_iso
    }
    try:
        response = requests.post("https://api.github.com/graphql", headers=headers, json={"query": query, "variables": variables}, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL error for period {from_date_iso}-{to_date_iso}: {data['errors']}", file=sys.stderr)
            return 0
        contrib_data = data.get("data", {}).get("user", {}).get("contributionsCollection", {}).get("contributionCalendar", {})
        return contrib_data.get("totalContributions", 0)
    except Exception as e:
        print(f"Exception fetching contributions for {from_date_iso}-{to_date_iso}: {e}", file=sys.stderr)
        return 0


def fetch_github_graphql_data():
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
        
        created_at_str = "2008-01-01T00:00:00Z" # Default fallback
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
        
        created_at_date = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        current_year = datetime.utcnow().year
        created_year = created_at_date.year
        
        # --- Calculate All-Time Contributions by iterating through years ---
        print("\nStep 2: Calculating All-Time Contributions by year...")
        all_time_contributions_sum = 0
        for year in range(created_year, current_year + 1):
            year_start_date_str = f"{year}-01-01T00:00:00Z"
            year_end_date_str = f"{year}-12-31T23:59:59Z"

            # Adjust for the first year (use actual createdAt if it's not Jan 1)
            if year == created_year:
                year_start_date_str = created_at_str
            
            # Adjust for the current year (use current datetime if it's not Dec 31)
            if year == current_year:
                year_end_date_str = datetime.utcnow().isoformat() + "Z"
            
            print(f"Fetching contributions for {GITHUB_USERNAME} from {year_start_date_str} to {year_end_date_str}")
            yearly_contribs = get_contributions_for_period(GITHUB_USERNAME, year_start_date_str, year_end_date_str)
            print(f"Contributions in {year}: {yearly_contribs}")
            all_time_contributions_sum += yearly_contribs
            # Optional: Add a small delay if making many API calls, though usually not needed for just a few years
            # import time
            # time.sleep(0.2) 

        stats["totalContributionsAllTime"] = all_time_contributions_sum
        print(f"Total All-Time Contributions calculated: {stats['totalContributionsAllTime']}")

        # --- Calculate Last Year Contributions ---
        print("\nStep 3: Calculating Last Year Contributions...")
        today_utc = datetime.utcnow()
        one_year_ago_utc = today_utc - timedelta(days=365) # 정확히 365일 전
        last_year_from_date_iso = one_year_ago_utc.isoformat() + "Z"
        to_date_iso = today_utc.isoformat() + "Z"
        
        stats["totalContributionsLastYear"] = get_contributions_for_period(GITHUB_USERNAME, last_year_from_date_iso, to_date_iso)
        print(f"Total Last Year Contributions: {stats['totalContributionsLastYear']}")

        # --- Fetch Repos, Followers, Following (can be one query) ---
        print("\nStep 4: Fetching Repositories, Followers, Following...")
        other_stats_query_body = """
        query($userName: String!) {
          user(login: $userName) {
            repositories(first: 100, ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
              totalCount
              nodes { stargazerCount isPrivate }
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
            repo_data = user_data_other.get("repositories")
            if repo_data:
                stats["totalRepositories"] = repo_data.get("totalCount", 0)
                current_repos = repo_data.get("nodes", [])
                stats["totalStarsReceived"] = sum(repo.get("stargazerCount", 0) for repo in current_repos)
                stats["publicRepositories"] = sum(1 for repo in current_repos if not repo.get("isPrivate"))
                stats["privateRepositories"] = stats["totalRepositories"] - stats["publicRepositories"] if stats["totalRepositories"] >= stats["publicRepositories"] else 0
            else: print("WARN: Repositories data missing.", file=sys.stderr)

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
        stats["errorFetching"] = f"HTTP error: {http_err} - Response: {http_err.response.text[:200]}"
        print(stats["errorFetching"], file=sys.stderr)
    except requests.exceptions.RequestException as req_err:
        stats["errorFetching"] = f"Network Error: {req_err}"
        print(stats["errorFetching"], file=sys.stderr)
    except Exception as e:
        stats["errorFetching"] = f"Unexpected error: {e}"
        print(stats["errorFetching"], file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    
    return stats

def save_stats_to_json(stats_data, filepath):
    try:
        with open(filepath, 'w') as f:
            json.dump(stats_data, f, indent=4)
        print(f"\nSuccessfully updated stats at {filepath}")
        print(f"Final data written: {json.dumps(stats_data)}")
    except IOError as e:
        print(f"\nError writing JSON file to {filepath}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print(f"--- Starting GitHub Stats Update Script for {GITHUB_USERNAME} ---")
    github_stats_data = fetch_github_graphql_data()
    if github_stats_data.get("errorFetching"):
        print(f"\n--- ERRORS RECORDED ---", file=sys.stderr)
        print(f"Error details: {github_stats_data['errorFetching']}", file=sys.stderr)
        print(f"Stats data might be incomplete or default to zeros.", file=sys.stderr)
    else:
        print("\n--- Data fetching appears to have completed without recorded errors. ---")
    save_stats_to_json(github_stats_data, OUTPUT_FILE_PATH)
    print(f"\n--- GitHub Stats Update Script Finished at {datetime.utcnow().isoformat() + 'Z'} ---")