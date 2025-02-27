import os
import requests
import openai
import base64
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Environment Variables
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# Validate Secrets
if not all([GITHUB_TOKEN, OPENAI_API_KEY, REPO_NAME]):
    logger.critical("❌ Missing required environment variables. Ensure PAT_TOKEN, OPENAI_API_KEY, and REPO_NAME are set.")
    exit(1)

# Constants
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4o"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."

def get_latest_pr_number():
    """Fetch the latest open PR number."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        prs = response.json()
        return prs[0]["number"] if prs else None
    except requests.RequestException as e:
        logger.error(f"Error fetching latest PR number: {e}")
        return None

def get_pr_branch(pr_number):
    """Fetch PR branch name."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json().get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
        return None

def get_modified_files(pr_number):
    """Fetch modified files in the PR."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []

def get_file_content(file_path, branch_name):
    """Fetch the content of a modified file."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return base64.b64decode(response.json().get("content", "")).decode("utf-8")
    except requests.RequestException as e:
        logger.error(f"Error fetching file content: {e}")
        return None

def review_code(file_path, file_content):
    """Send code for AI review and parse response safely."""
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
        logger.info(f"AI response received for {file_path}")
        return json.loads(ai_response[ai_response.find("{") : ai_response.rfind("}") + 1])
    except (openai.error.OpenAIError, json.JSONDecodeError) as e:
        logger.error(f"AI review failed for {file_path}: {e}")
        return {"review": "AI response could not be parsed.", "comments": []}

def get_latest_commit_sha(pr_number):
    """Fetch the latest commit SHA of a PR."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        commits = response.json()
        return commits[-1]["sha"] if commits else None
    except requests.RequestException as e:
        logger.error(f"Error fetching latest commit SHA: {e}")
        return None

def post_inline_comments(pr_number, file_path, comments):
    """Post inline comments on a PR."""
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id:
        return

    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
    for comment in comments:
        payload = {
            "body": f"{comment['comment']}\n\n**Suggested Code:**\n```{file_path.split('.')[-1]}\n{comment['suggested_code']}\n```",
            "commit_id": commit_id,
            "path": file_path,
            "side": "RIGHT",
            "line": comment["line"]
        }
        try:
            response = requests.post(url, headers=GITHUB_HEADERS, json=payload)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to post inline comment: {e}")

def post_pr_comment(pr_number, review):
    """Post an overall PR comment."""
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
    try:
        response = requests.post(url, headers=GITHUB_HEADERS, json={"body": review})
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to post PR comment: {e}")

if __name__ == "__main__":
    pr_number = get_latest_pr_number()
    if not pr_number:
        logger.info("No open PRs found.")
        exit()

    pr_branch = get_pr_branch(pr_number)
    if not pr_branch:
        logger.error("Failed to fetch PR branch.")
        exit()

    files = get_modified_files(pr_number)
    if not files:
        logger.info("No modified files found in the PR.")
        exit()

    full_review = ""
    for file in files:
        file_path = file["filename"]
        file_content = get_file_content(file_path, pr_branch)
        if not file_content:
            continue

        review_data = review_code(file_path, file_content)
        logger.info(f"Review for {file_path}: {review_data}")

        if "comments" in review_data:
            post_inline_comments(pr_number, file_path, review_data["comments"])

        full_review += f"### {file_path}\n{review_data.get('review', 'No review available')}\n\n"

    post_pr_comment(pr_number, full_review)
