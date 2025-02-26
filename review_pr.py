import os
import requests
import openai
import base64
import json
import logging

# Load environment variables from GitHub Secrets
GITHUB_TOKEN = os.getenv("PAT_TOKEN")  # Use `get()` to avoid crashes

if not GITHUB_TOKEN:
    raise ValueError("❌ PAT_TOKEN environment variable is missing. Ensure it is set in GitHub Secrets.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# GitHub API headers
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Setup logging
logging.basicConfig(level=logging.INFO)

def get_latest_pr_number():
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        return response.json()[0]["number"]
    logging.error("No open PRs found or failed to fetch PRs.")
    return None

def get_pr_branch(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json()["head"]["ref"]
    logging.error(f"Failed to fetch PR branch: {response.json()}")
    return None

def get_modified_files(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        logging.error("Failed to fetch PR files: %s", response.json())
        return []
    return response.json()

def get_file_content(file_path, branch_name):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    logging.warning(f"Skipping missing file: {file_path} (Not found in branch {branch_name})")
    return None

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

    Respond strictly in valid JSON format.
    """
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer. Always respond in JSON format."},
            {"role": "user", "content": prompt}
        ]
    )
    try:
        return json.loads(response.choices[0].message.content.strip())
    except json.JSONDecodeError:
        logging.error("Failed to parse AI response: %s", response.choices[0].message.content)
        return {"review": "AI response could not be parsed.", "comments": []}

def post_inline_comments(pr_number, file_path, comments):
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id:
        logging.error("Failed to fetch commit SHA for %s. Skipping inline comments.", file_path)
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
            "line": comment["line"]
        }
        url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/comments"
        response = requests.post(url, headers=HEADERS, json=comment_payload)
        if response.status_code == 201:
            logging.info("Successfully posted inline comment on %s, line %d", file_path, comment['line'])
        else:
            logging.error("Failed to post inline comment: %s", response.json())

def post_pr_comment(pr_number, review):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{pr_number}/comments"
    data = {"body": review}
    response = requests.post(url, headers=HEADERS, json=data)
    if response.status_code == 201:
        logging.info("Successfully posted AI review comment.")
    else:
        logging.error("Failed to post PR comment: %s", response.json())

def get_latest_commit_sha(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200 and response.json():
        return response.json()[-1]["sha"]
    logging.error("Failed to fetch latest commit SHA.")
    return None

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
