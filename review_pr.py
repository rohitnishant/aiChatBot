import os
import requests
import openai
import base64
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# Constants
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4o-mini"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."

# Validate Environment Variables
required_env_vars = {"PAT_TOKEN": GITHUB_TOKEN, "OPENAI_API_KEY": OPENAI_API_KEY, "REPO_NAME": REPO_NAME}
missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}. Ensure they are set in GitHub Secrets.")

def get_latest_pr_number():
    """Fetch the latest open pull request number."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        prs = response.json()
        return prs[0]["number"] if prs else None
    except requests.RequestException as e:
        logger.error(f"Error fetching latest PR number: {e}")
        return None

def get_pr_branch(pr_number):
    """Fetch the branch name associated with a pull request."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json().get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
        return None

def get_modified_files(pr_number):
    """Retrieve the list of modified files in the pull request."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []

def get_file_content(file_path, branch_name):
    """Retrieve the content of a file from the pull request branch."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    except requests.HTTPError as e:
        if response.status_code == 404:
            logger.warning(f"Skipping missing file: {file_path} (Not found in branch {branch_name})")
        else:
            logger.error(f"Error fetching file content: {e}")
        return None

def review_code(file_path, file_content):
    """Send the file content to OpenAI for review and return structured feedback."""
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
    {{
        "review": "Overall review text here.",
        "comments": [
            {{"line": 12, "comment": "Consider refactoring this loop to use a dictionary lookup.", "suggested_code": "new_code_here"}}
        ]
    }}
    """
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": AI_ROLE}, {"role": "user", "content": prompt}]
        )
        ai_response = response.choices[0].message.content.strip()
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}")
        if json_start == -1 or json_end == -1:
            logger.error(f"Invalid AI response format: {ai_response}")
            return {"review": "AI review could not be generated.", "comments": []}
        logger.info(json.loads(ai_response[json_start : json_end + 1]))
        return json.loads(ai_response[json_start : json_end + 1])

    except (openai.OpenAIError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error reviewing code: {e}")
        return {"review": "AI response could not be parsed.", "comments": []}

def get_latest_commit_sha(pr_number):
    """Retrieve the latest commit SHA for the pull request."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        commits = response.json()
        return commits[-1]["sha"] if commits else None
    except requests.RequestException as e:
        logger.error(f"Error fetching latest commit SHA: {e}")
        return None

def post_inline_comments(pr_number, file_path, comments):
    """Post inline comments for the pull request."""
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
        try:
            url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
            response = requests.post(url, headers=GITHUB_HEADERS, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully posted inline comment on {file_path}, line {comment['line']}")
        except requests.RequestException as e:
            logger.error(f"Error posting inline comment: {e}")

def post_pr_comment(pr_number, review):
    """Post an overall PR review comment."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
        response = requests.post(url, headers=GITHUB_HEADERS, json={"body": review})
        response.raise_for_status()
        logger.info("Successfully posted AI review comment.")
    except requests.RequestException as e:
        logger.error(f"Error posting PR comment: {e}")

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
