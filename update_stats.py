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
    "Authorization": f"bearer {GITHUB_TOKEN}" # Use 'bearer' for GraphQL
}

if not GITHUB_TOKEN:
    print("CRITICAL ERROR: GH_PAT secret not found. This script requires an authenticated PAT to access contribution data.", file=sys.stderr)
    print("Please ensure GH_PAT is set as a secret in your GitHub Actions workflow.", file=sys.stderr)
    sys.exit(1) # Exit if no token, as GraphQL calls will fail or be severely limited.

def fetch_github_graphql_data():
    """Fetches required data from the GitHub GraphQL API."""
    stats = {
        "username": GITHUB_USERNAME,
        "totalContributionsLastYear": 0,
        "totalRepositories": 0,
        "publicRepositories": 0,
        "privateRepositories": 0, # Derived
        "followers": 0,
        "following": 0,
        "totalStarsReceived": 0,
        "dataFetchedAt": datetime.utcnow().isoformat() + "Z"
    }

    # Define date range for the last year for contributions
    today = datetime.utcnow()
    one_year_ago = today - timedelta(days=365)
    
    # Format dates for GraphQL (ISO 8601)
    from_date_iso = one_year_ago.isoformat() + "Z"
    to_date_iso = today.isoformat() + "Z"

    graphql_query_body = """
    query($userName: String!, $fromDate: DateTime!, $toDate: DateTime!) {
      user(login: $userName) {
        contributionsCollection(from: $fromDate, to: $toDate) {
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
          pageInfo {
            endCursor
            hasNextPage
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
    
    graphql_query = {
        "query": graphql_query_body,
        "variables": {
            "userName": GITHUB_USERNAME,
            "fromDate": from_date_iso,
            "toDate": to_date_iso
        }
    }

    try:
        response = requests.post("https://api.github.com/graphql", headers=headers, json=graphql_query)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        data = response.json()

        if "errors" in data:
            print(f"GraphQL query errors: {data['errors']}", file=sys.stderr)

        user_data = data.get("data", {}).get("user", {})

        if user_data:
            # Contributions
            contributions_data = user_data.get("contributionsCollection", {}).get("contributionCalendar", {})
            if contributions_data:
                stats["totalContributionsLastYear"] = contributions_data.get("totalContributions", 0)

            # Repositories, Stars, Public/Private Count
            repo_data = user_data.get("repositories", {})
            if repo_data:
                stats["totalRepositories"] = repo_data.get("totalCount", 0)
                

                current_repos = repo_data.get("nodes", [])
                total_stars = 0
                public_repo_count = 0
                
                # Initial fetch for stars and public/private count
                for repo in current_repos:
                    total_stars += repo.get("stargazerCount", 0)
                    if not repo.get("isPrivate", True): # Assume private if field missing, though it should be there
                        public_repo_count += 1
                


                stats["publicRepositories"] = public_repo_count # This is from the first 100
                all_repos_nodes = current_repos # placeholder for potentially paginated list
                
                # Re-calculate public/private from the nodes we have (up to 100)
                calculated_public_repos = sum(1 for repo in all_repos_nodes if not repo.get("isPrivate"))
                stats["publicRepositories"] = calculated_public_repos
                stats["privateRepositories"] = stats["totalRepositories"] - calculated_public_repos


                stats["totalStarsReceived"] = total_stars # Stars from first 100 repos

            # Followers & Following
            if user_data.get("followers"):
                stats["followers"] = user_data.get("followers").get("totalCount", 0)
            if user_data.get("following"):
                stats["following"] = user_data.get("following").get("totalCount", 0)
        else:
            print("User data not found in GraphQL response.", file=sys.stderr)


    except requests.exceptions.RequestException as e:
        print(f"Error fetching GitHub GraphQL data: {e}", file=sys.stderr)
        # Potentially return current stats or default stats to avoid breaking the file
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from GraphQL response: {e}", file=sys.stderr)
        print(f"Response text: {response.text[:500]}...", file=sys.stderr) # Print first 500 chars of response

    return stats

def save_stats_to_json(stats_data, filepath):
    """Saves the statistics to a JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(stats_data, f, indent=4)
        print(f"Successfully updated stats at {filepath}")
        print(f"Data: {json.dumps(stats_data)}") # Print the data that was written
    except IOError as e:
        print(f"Error writing JSON file to {filepath}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print(f"Running script to update GitHub stats for user: {GITHUB_USERNAME} using GraphQL")
    
    github_stats_data = fetch_github_graphql_data()
    save_stats_to_json(github_stats_data, OUTPUT_FILE_PATH)
    
    print("Script finished.")