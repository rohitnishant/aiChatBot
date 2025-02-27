import os
import requests
import openai
import base64
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# Environment variable validation
if not GITHUB_TOKEN:
    logger.error("❌ PAT_TOKEN environment variable is missing.")
    exit(1)
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY environment variable is missing.")
    exit(1)
if not REPO_NAME:
    logger.error("❌ REPO_NAME environment variable is missing.")
    exit(1)

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4o-mini"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."

def get_latest_pr_number():
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
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json().get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
        return None

def get_modified_files(pr_number):
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []

def get_file_content(file_path, branch_name):
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    except requests.RequestException as e:
        logger.error(f"Error fetching file content: {e}")
        return None

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
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": AI_ROLE}, {"role": "user", "content": prompt}]
        )
        ai_response = response.choices[0].message.content.strip()
        logger.info(f"AI response: {ai_response}")
        return json.loads(ai_response[ai_response.find("{") : ai_response.rfind("}") + 1])
    except (openai.error.OpenAIError, json.JSONDecodeError) as e:
        logger.error(f"Error reviewing code: {e}")
        return {"review": "AI response could not be parsed.", "comments": []}

def get_latest_commit_sha(pr_number):
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
        except requests.RequestException as e:
            logger.error(f"Error posting inline comment: {e}")

def post_pr_comment(pr_number, review):
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
        response = requests.post(url, headers=GITHUB_HEADERS, json={"body": review})
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error posting PR comment: {e}")

if __name__ == "__main__":
    PR_NUMBER = get_latest_pr_number()
    if not PR_NUMBER:
        logger.info("No open PRs found.")
        exit()
    PR_BRANCH = get_pr_branch(PR_NUMBER)
    if not PR_BRANCH:
        logger.error("Failed to fetch PR branch.")
        exit()
    files = get_modified_files(PR_NUMBER)
    if not files:
        logger.info("No modified files found in the PR.")
        exit()
    full_review = ""
    for file in files:
        file_path = file["filename"]
        file_content = get_file_content(file_path, PR_BRANCH)
        if not file_content:
            continue
        review_data = review_code(file_path, file_content)
        logger.info(f"Review for {file_path}: {review_data}")
        if review_data.get("comments"):
            post_inline_comments(PR_NUMBER, file_path, review_data["comments"])
        full_review += f"### {file_path}\n{review_data.get('review', 'No review found.')}\n\n"
    post_pr_comment(PR_NUMBER, full_review)
