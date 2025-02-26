import os
import requests
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

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

# Step 3: Extract Code Diff
def get_code_diff(files):
    diffs = []
    for file in files:
        filename = file["filename"]
        patch = file.get("patch", "")  # Patch contains code diff
        diffs.append(f"File: {filename}\nDiff:\n{patch}\n\n")
    
    return "\n".join(diffs)

# Step 4: Call ChatGPT API for Code Review
def review_code_with_chatgpt(code_diff):
    prompt = f"""
    You are an AI code reviewer. Analyze the following GitHub pull request code changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    
    Code Diff:
    {code_diff}
    
    Provide a structured review with clear and constructive comments.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response["choices"][0]["message"]["content"]

# Step 5: Post AI Review as PR Comment
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

    print("Extracting code diffs...")
    code_diff = get_code_diff(files)

    print("Reviewing code with ChatGPT...")
    ai_review = review_code_with_chatgpt(code_diff)

    print("Posting AI review as a PR comment...")
    post_pr_comment(PR_NUMBER, ai_review)