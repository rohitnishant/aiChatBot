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

# Step 2: Fetch PR Branch Name
def get_pr_branch(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json()["head"]["ref"]  # PR branch name
    else:
        print(f"❌ Failed to fetch PR branch: {response.json()}")
        return None

# Step 3: Fetch PR Files
def get_modified_files(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print("Failed to fetch PR files:", response.json())
        return []
    
    return response.json()

# Step 4: Fetch File Content from PR Branch
def get_file_content(file_path, branch_name):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        content = response.json()["content"]
        return base64.b64decode(content).decode("utf-8")
    elif response.status_code == 404:
        print(f"⚠️ Skipping missing file: {file_path} (Not found in branch {branch_name})")
    else:
        print(f"❌ Failed to fetch content for {file_path}: {response.json()}")

    return None

# Step 5: Call ChatGPT API for Code Review and Inline Comments
def review_code(file_path, file_content):
    language = file_path.split(".")[-1]
    
    prompt = f"""
    You are an AI code reviewer for {language}. Analyze the following file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    - Provide inline comments with line numbers and suggest improved code snippets.

    File Path: {file_path}
    Code:
    {file_content}

    Respond strictly in valid JSON format:
    ```
    {{
        "review": "Overall review text here.",
        "comments": [
            {{"line": 12, "comment": "Consider refactoring this loop to use a dictionary lookup instead of multiple if conditions.", "suggested_code": "new_code_here"}},
            {{"line": 25, "comment": "Avoid hardcoding API keys. Use environment variables instead.", "suggested_code": "new_code_here"}}
        ]
    }}
    ```
    """
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer. Always respond strictly in JSON format."},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        ai_response = response.choices[0].message.content.strip()
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}")
        
        if json_start == -1 or json_end == -1:
            print(f"⚠️ Unexpected AI response: {ai_response}")
            return {"review": "AI response could not be parsed.", "comments": []}
        
        return json.loads(ai_response[json_start : json_end + 1])

    except json.JSONDecodeError:
        print(f"❌ Failed to parse AI response: {response.choices[0].message.content}")
        return {"review": "AI response could not be parsed.", "comments": []}

# Step 6: Post Inline PR Comments
def post_inline_comments(pr_number, file_path, comments):
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id:
        print(f"❌ Failed to fetch commit SHA for {file_path}. Skipping inline comments.")
        return

    for comment in comments:
        comment_body = comment["comment"]
        if "suggested_code" in comment and comment["suggested_code"]:
            comment_body += f"\n\n**Suggested Code:**\n```{file_path.split('.')[-1]}\n{comment['suggested_code']}\n```"

        comment_payload = {
            "body": comment_body,
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

# Step 7: Post Overall AI Review as PR Comment
def post_pr_comment(pr_number, review):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{pr_number}/comments"
    data = {"body": review}
    
    response = requests.post(url, headers=HEADERS, json=data)
    
    if response.status_code == 201:
        print("✅ Successfully posted AI review comment.")
    else:
        print(f"❌ Failed to post PR comment: {response.json()}")

# Step 8: Get Latest Commit SHA
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
    
    print("Fetching PR branch name...")
    PR_BRANCH = get_pr_branch(PR_NUMBER)
    
    if not PR_BRANCH:
        print("❌ Could not determine PR branch. Exiting...")
        exit()
    
    print(f"PR Branch: {PR_BRANCH}")
    
    print("Fetching modified files...")
    files = get_modified_files(PR_NUMBER)
    
    if not files:
        print("No modified files found. Exiting...")
        exit()
    
    full_review = ""

    for file in files:
        file_path = file["filename"]
        print(f"Processing file: {file_path}")
        
        file_content = get_file_content(file_path, PR_BRANCH)
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
