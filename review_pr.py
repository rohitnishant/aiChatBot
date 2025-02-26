import os
import requests
import openai
import base64
import json

# Load environment variables from GitHub Secrets
GITHUB_TOKEN = os.getenv("PAT_TOKEN")  # Use `get()` to avoid crashes

if not GITHUB_TOKEN:
    raise ValueError("❌ PAT_TOKEN environment variable is missing. Ensure it is set in GitHub Secrets.")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
REPO_NAME = os.environ["REPO_NAME"]

# GitHub API headers
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Step 1: Fetch the Latest Open PR Number
def get_latest_pr_number():
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        latest_pr = response.json()[0]  # Get the most recent open PR
        return latest_pr["number"]
    else:
        print("No open PRs found or failed to fetch PRs.")
        return None

# Step 2: Fetch PR Files
def get_modified_files(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print("Failed to fetch PR files:", response.json())
        return []
    
    return response.json()

# Step 3: Fetch PR Branch Name
def get_pr_branch(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json()["head"]["ref"]  # PR branch name
    else:
        print(f"❌ Failed to fetch PR branch: {response.json()}")
        return None

# Step 4: Call ChatGPT API for Code Review and Inline Comments
def review_code(file_path, file_content):
    prompt = f"""
    You are an AI code reviewer. Analyze the following GitHub pull request file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    Additionally, provide inline comments with line numbers where improvements are needed.

    File Path: {file_path}
    Code:
    {file_content}
    
    Return structured JSON like this:
    {{
        "review": "Overall review text here.",
        "comments": [
            {{ "line": 12, "comment": "Consider refactoring this loop to use a dictionary lookup instead of multiple if conditions." }},
            {{ "line": 25, "comment": "Avoid hardcoding API keys. Use environment variables instead." }}
        ]
    }}
    """
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer."},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        print("❌ Failed to parse AI response.")
        return {"review": "", "comments": []}

# Step 5: Post Inline PR Comments
def post_inline_comments(pr_number, file_path, comments):
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id:
        print(f"❌ Failed to fetch commit SHA for {file_path}. Skipping inline comments.")
        return

    for comment in comments:
        comment_payload = {
            "body": comment["comment"],
            "commit_id": commit_id,
            "path": file_path,
            "side": "RIGHT",
            "line": comment["line"]  # Must match PR diff line number
        }

        url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/comments"
        response = requests.post(url, headers=HEADERS, json=comment_payload)

        if response.status_code == 201:
            print(f"✅ Successfully posted inline comment on {file_path}, line {comment['line']}")
        else:
            print(f"❌ Failed to post inline comment: {response.json()}")

# Step 6: Post Overall AI Review as PR Comment
def post_pr_comment(pr_number, review):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{pr_number}/comments"
    data = {"body": review}
    
    response = requests.post(url, headers=HEADERS, json=data)
    
    if response.status_code == 201:
        print("✅ Successfully posted AI review comment.")
    else:
        print("❌ Failed to post PR comment:", response.json())

# Step 7: Get Latest Commit SHA
def get_latest_commit_sha(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        return response.json()[-1]["sha"]  # Get latest commit SHA
    else:
        print("❌ Failed to fetch latest commit SHA.")
        return None

# Main Execution Flow
if __name__ == "__main__":
    print("Fetching latest open PR number...")
    PR_NUMBER = get_latest_pr_number()
    
    if not PR_NUMBER:
        print("No open PRs found. Exiting...")
        exit()

    print(f"Latest PR number: {PR_NUMBER}")
    
    print("Fetching modified files...")
    files = get_modified_files(PR_NUMBER)
    
    if not files:
        print("No modified files found. Exiting...")
        exit()
    
    full_review = ""
    
    for file in files:
        file_path = file["filename"]
        print(f"Processing file: {file_path}")
        
        file_content = get_file_content(file_path)
        if not file_content:
            continue
        
        print("Reviewing file...")
        review_data = review_code(file_path, file_content)
        
        if review_data["comments"]:
            print("Posting inline comments...")
            post_inline_comments(PR_NUMBER, file_path, review_data["comments"])
        
        full_review += f"### {file_path}\n{review_data['review']}\n\n"
    
    print("Posting AI review as a PR comment...")
    post_pr_comment(PR_NUMBER, full_review)
