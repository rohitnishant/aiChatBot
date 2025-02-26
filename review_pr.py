import os
import requests
import openai
import base64

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

# Step 3: Fetch File Content
def get_file_content(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        content = response.json()["content"]
        return base64.b64decode(content).decode("utf-8")
    else:
        print(f"Failed to fetch content for {file_path}: {response.json()}")
        return None

# Step 4: Call ChatGPT API for Code Review and Fixes
def review_and_fix_code(file_path, file_content):
    prompt = f"""
    You are an AI code reviewer. Analyze the following GitHub pull request file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    Additionally, suggest improved code replacements where needed.

    File Path: {file_path}
    Code:
    {file_content}
    """
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content

# Step 5: Commit Improved Code
def commit_code_changes(file_path, improved_code, pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    
    # Fetch file metadata
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"❌ Failed to fetch file metadata for {file_path}: {response.json()}")
        return
    
    sha = response.json()["sha"]  # Needed to update the file
    encoded_content = base64.b64encode(improved_code.encode("utf-8")).decode("utf-8")
    
    data = {
        "message": f"AI Code Improvement for {file_path} in PR #{pr_number}",
        "content": encoded_content,
        "sha": sha,
        "branch": f"refs/pull/{pr_number}/head"
    }
    
    commit_response = requests.put(url, headers=HEADERS, json=data)
    if commit_response.status_code == 200:
        print(f"✅ Successfully committed improvements to {file_path}")
    else:
        print(f"❌ Failed to commit improvements for {file_path}: {commit_response.json()}")

# Step 6: Post AI Review as PR Comment
def post_pr_comment(pr_number, review):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{pr_number}/comments"
    data = {"body": review}
    
    response = requests.post(url, headers=HEADERS, json=data)
    
    if response.status_code == 201:
        print("Successfully posted AI review comment.")
    else:
        print("Failed to post PR comment:", response.json())

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
    
    for file in files:
        file_path = file["filename"]
        print(f"Processing file: {file_path}")
        
        file_content = get_file_content(file_path)
        if not file_content:
            continue
        
        print("Reviewing and improving code...")
        improved_code = review_and_fix_code(file_path, file_content)
        
        print("Committing improvements...")
        commit_code_changes(file_path, improved_code, PR_NUMBER)
    
    print("Posting AI review as a PR comment...")
    post_pr_comment(PR_NUMBER, "AI-generated code improvements have been committed. Please review the changes.")
