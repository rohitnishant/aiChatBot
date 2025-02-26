import os
import requests
import openai
import base64
import json

GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

if not GITHUB_TOKEN:
    raise ValueError("❌ PAT_TOKEN environment variable is missing. Ensure it is set in GitHub Secrets.")
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."


 # Fetch latest PR number
def get_latest_pr_number():
    
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    response = requests.get(url, headers=GITHUB_HEADERS)
    return response.json()[0]["number"] if response.status_code == 200 and response.json() else None

 # Fetch PR branch name
def get_pr_branch(pr_number):
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=GITHUB_HEADERS)
    return response.json().get("head", {}).get("ref") if response.status_code == 200 else None

 # Fetch modified files
def get_modified_files(pr_number):   
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=GITHUB_HEADERS)
    return response.json() if response.status_code == 200 else []

# Fetch file content from branch
def get_file_content(file_path, branch_name):
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    response = requests.get(url, headers=GITHUB_HEADERS)
    if response.status_code == 200:
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    return None

# Analyze code with OpenAI
def review_code(file_path, file_content):
    
    language = file_path.split(".")[-1]
    prompt = (
        f"""
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
        {{
            "review": "Overall review text here.",
            "comments": [
                {{"line": 12, "comment": "Consider refactoring this loop to use a dictionary lookup.", "suggested_code": "new_code_here"}}
            ]
        }}
        """
    )
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": AI_ROLE}, {"role": "user", "content": prompt}]
    )
    try:
        ai_response = response.choices[0].message.content.strip()
        return json.loads(ai_response[ai_response.find("{") : ai_response.rfind("}") + 1])
    except json.JSONDecodeError:
        return {"review": "AI response could not be parsed.", "comments": []}

# Get latest commit SHA
def get_latest_commit_sha(pr_number):
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=GITHUB_HEADERS)
    return response.json()[-1]["sha"] if response.status_code == 200 and response.json() else None

# Post inline PR comments
def post_inline_comments(pr_number, file_path, comments):
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id:
        return
    for comment in comments:
        payload = {
            "body": f"{comment['comment']}\n\n**Suggested Code:**\n```{file_path.split('.')[-1]}\n{comment['suggested_code']}\n```",
            "commit_id": commit_id,
            "path": file_path,
            "side": "RIGHT",
            "line": comment["line"]
        }
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
        requests.post(url, headers=GITHUB_HEADERS, json=payload)

 # Post PR review comment
def post_pr_comment(pr_number, review):
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
    requests.post(url, headers=GITHUB_HEADERS, json={"body": review})

# Main execution flow
if __name__ == "__main__":
    
    PR_NUMBER = get_latest_pr_number()
    if not PR_NUMBER:
        exit()
    PR_BRANCH = get_pr_branch(PR_NUMBER)
    if not PR_BRANCH:
        exit()
    files = get_modified_files(PR_NUMBER)
    if not files:
        exit()
    full_review = ""
    for file in files:
        file_path = file["filename"]
        file_content = get_file_content(file_path, PR_BRANCH)
        if not file_content:
            continue
        review_data = review_code(file_path, file_content)
        if review_data["comments"]:
            post_inline_comments(PR_NUMBER, file_path, review_data["comments"])
        full_review += f"### {file_path}\n{review_data['review']}\n\n"
    post_pr_comment(PR_NUMBER, full_review)