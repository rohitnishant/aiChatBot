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
missing_vars = [var for var, value in {"PAT_TOKEN": GITHUB_TOKEN, "OPENAI_API_KEY": OPENAI_API_KEY, "REPO_NAME": REPO_NAME}.items() if not value]
if missing_vars:
    logger.critical(f"❌ Missing required environment variables: {', '.join(missing_vars)}. Ensure they are set.")
    exit(1)

# Constants
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_REPO_URL = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4o"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."

# Handles API GET requests with error handling and logging for GitHub API.
# Built a genric function for fetch api's
def fetch_api(endpoint):
    url = f"{GITHUB_API_REPO_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"API GET request failed: {url} | Error: {e}")
        return None

#Handles API POST requests with error handling and logging for GitHub API.
def post_api(endpoint, payload):
    """Handles API POST requests with error handling."""
    url = f"{GITHUB_API_REPO_URL}/{endpoint}"
    try:
        response = requests.post(url, headers=GITHUB_HEADERS, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"API POST request failed: {url} | Error: {e}")
        return None

# Fetch the latest open PR number.
def get_latest_pr_number():
    prs = fetch_api("pulls?state=open&sort=created&direction=desc")
    return prs[0]["number"] if prs else None

#Fetch the branch name for a given PR.
def get_pr_branch(pr_number):
    pr_data = fetch_api(f"pulls/{pr_number}")
    return pr_data.get("head", {}).get("ref") if pr_data else None

#Fetch the list of modified files in a PR.
def get_modified_files(pr_number):
    return fetch_api(f"pulls/{pr_number}/files") or []

#Fetch the content of a modified file.
def get_file_content(file_path, branch_name):
    file_data = fetch_api(f"contents/{file_path}?ref={branch_name}")
    if file_data and "content" in file_data:
        return base64.b64decode(file_data["content"]).decode("utf-8")
    return None

#  Sends code to OpenAI GPT-4o for review.
#     The AI will provide feedback on:
#     - Code quality and best practices
#     - Readability and maintainability
#     - Performance improvements
#     - Security vulnerabilities
#     - Inline comments with suggested fixes

# it will provide a general review comment for the PR
# it can review multiple files in a PR
# it can review code in any programming language , it will detect the language from the file extension and became coder revier for that language
# it can provide inline comments with line numbers and suggested code snippets
# we can change the prompt the way we want to ask the AI to review the code in the file
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

# Retrieve the latest commit SHA for a given PR
def get_latest_commit_sha(pr_number):
    commits = fetch_api(f"pulls/{pr_number}/commits")
    return commits[-1]["sha"] if commits else None

# Post inline comments on GitHub PR for specific lines
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
        post_api(f"pulls/{pr_number}/comments", payload)

# Post a general review comment on the PR
def post_pr_comment(pr_number, review):
    post_api(f"issues/{pr_number}/comments", {"body": review})

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
