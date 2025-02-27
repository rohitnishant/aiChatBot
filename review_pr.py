import os
import requests
import openai
import base64
import json
import logging
from typing import Optional, Dict, List

# -----------------------------------------------------
# Logging & Environment
# -----------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

REQUIRED_ENV_VARS = {
    "PAT_TOKEN": GITHUB_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "REPO_NAME": REPO_NAME,
}
missing_vars = [var for var, val in REQUIRED_ENV_VARS.items() if not val]
if missing_vars:
    raise ValueError(
        f"Missing environment variables: {', '.join(missing_vars)}. "
        "Ensure they are set in GitHub Secrets."
    )

# -----------------------------------------------------
# Constants & Configuration
# -----------------------------------------------------

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Set OpenAI credentials
openai.api_key = OPENAI_API_KEY

# For Python 3.9, no union pipe syntax. We'll use "Optional[...]".
OPENAI_MODEL = "gpt-4o-mini"
AI_SYSTEM_ROLE = (
    "You are a professional software code reviewer. Always respond strictly in JSON format."
)

CATEGORIES = [
    "overall_review",
    "code_quality_and_best_practices",
    "readability_and_maintainability",
    "efficiency_and_performance_improvements",
    "security_vulnerabilities",
]

# -----------------------------------------------------
# GitHub API Functions
# -----------------------------------------------------

def get_latest_pr_number() -> Optional[int]:
    """
    Retrieve the latest open PR number for the repository.
    Returns:
        Optional[int]: The latest open PR number if found, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls"
        params = {"state": "open", "sort": "created", "direction": "desc"}
        resp = requests.get(url, headers=GITHUB_HEADERS, params=params)
        resp.raise_for_status()
        pulls = resp.json()
        if pulls:
            return pulls[0]["number"]
        logger.info("No open PR found.")
    except requests.RequestException as e:
        logger.error(f"Error fetching latest PR number: {e}")
    return None


def get_pr_branch(pr_number: int) -> Optional[str]:
    """
    Retrieve the branch name for a given PR number.
    Args:
        pr_number (int): Pull request number.
    Returns:
        Optional[str]: The branch name if found, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
        resp = requests.get(url, headers=GITHUB_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        return data.get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
    return None


def get_modified_files(pr_number: int) -> List[Dict]:
    """
    Fetch the list of modified files for a given PR.
    Args:
        pr_number (int): Pull request number.
    Returns:
        list of dict: A list of file info objects from GitHub's API.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
        resp = requests.get(url, headers=GITHUB_HEADERS)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []


def get_file_content(file_path: str, branch_name: str) -> Optional[str]:
    """
    Retrieve file content from a specific PR branch.
    Args:
        file_path (str): Path to the file in the repository.
        branch_name (str): Branch name to fetch from.
    Returns:
        Optional[str]: The decoded file content if successful, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}"
        params = {"ref": branch_name}
        resp = requests.get(url, headers=GITHUB_HEADERS, params=params)
        resp.raise_for_status()
        content = resp.json()["content"]
        return base64.b64decode(content).decode("utf-8")
    except requests.RequestException as e:
        logger.error(f"Error fetching file content '{file_path}': {e}")
    return None


def get_latest_commit_sha(pr_number: int) -> Optional[str]:
    """
    Retrieve the latest commit SHA for a given PR.
    Args:
        pr_number (int): Pull request number.
    Returns:
        Optional[str]: The latest commit SHA if found, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
        resp = requests.get(url, headers=GITHUB_HEADERS)
        resp.raise_for_status()
        commits = resp.json()
        if commits:
            return commits[-1]["sha"]
    except requests.RequestException as e:
        logger.error(f"Error fetching latest commit SHA: {e}")
    return None

# -----------------------------------------------------
# OpenAI Review Function
# -----------------------------------------------------

def review_code(file_path: str, file_content: str) -> dict:
    """
    Send file content to OpenAI for code review and return structured feedback.
    The returned dict must contain:
      - overall_review: str
      - code_quality_and_best_practices: List[dict]
      - readability_and_maintainability: List[dict]
      - efficiency_and_performance_improvements: List[dict]
      - security_vulnerabilities: List[dict]
    Args:
        file_path (str): Path of the file being reviewed.
        file_content (str): Full text content of the file.
    Returns:
        dict: Structured feedback from OpenAI for each category.
    """
    language = file_path.split(".")[-1]
    prompt = f"""
    You are an AI code reviewer for {language}. Analyze the following file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    - Provide inline comments with line numbers and suggest improved code snippets.
    
    Additionally, generate an **overall_review** summarizing key findings.

    File Path: {file_path}
    Code:
    {file_content}

    Respond strictly in valid JSON format:
    {{
      "overall_review": "Summary of findings.",
      "code_quality_and_best_practices": [],
      "readability_and_maintainability": [],
      "efficiency_and_performance_improvements": [],
      "security_vulnerabilities": []
    }}
    """

    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": AI_SYSTEM_ROLE},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        ai_response = response.choices[0].message.content.strip()

        # Extract JSON from AI response
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}")
        if json_start == -1 or json_end == -1:
            raise ValueError("AI did not return valid JSON.")

        data = json.loads(ai_response[json_start : json_end + 1])

        # Ensure each category is present in final_data
        final_data = {}
        for cat in CATEGORIES:
            if cat == "overall_review":
                final_data[cat] = data.get(cat, "No overall review.")
            else:
                final_data[cat] = data.get(cat, [])
        return final_data

    except (json.JSONDecodeError, ValueError, Exception) as e:
        logger.error(f"Error reviewing code '{file_path}': {e}")
        return {
            "overall_review": "AI review could not be generated.",
            "code_quality_and_best_practices": [],
            "readability_and_maintainability": [],
            "efficiency_and_performance_improvements": [],
            "security_vulnerabilities": []
        }

# -----------------------------------------------------
# Posting Comments to GitHub
# -----------------------------------------------------

def post_inline_comments(pr_number: int, file_path: str, comments: list) -> None:
    """
    Post inline comments to GitHub for the specified PR and file.

    Args:
        pr_number (int): Pull request number.
        file_path (str): File path in the repo.
        comments (list): List of comment objects from AI (line, comment, etc.).
    """
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id or not comments:
        return

    for comment in comments:
        line = comment.get("line")
        text = comment.get("comment")
        if not line or not text:
            continue  # skip invalid

        payload = {
            "body": text,
            "commit_id": commit_id,
            "path": file_path,
            "side": "RIGHT",
            "line": line
        }
        try:
            url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
            resp = requests.post(url, headers=GITHUB_HEADERS, json=payload)
            resp.raise_for_status()
            logger.info(f"Posted inline comment on {file_path}, line {line}")
        except requests.RequestException as e:
            logger.error(f"Error posting inline comment on {file_path}, line {line}: {e}")

def post_pr_comment(pr_number: int, aggregated_data: dict) -> None:
    """
    Post a summarized AI review as a single PR comment.

    Args:
        pr_number: The pull request number.
        aggregated_data: Aggregated AI feedback from multiple files.
    """
    body = "## 🔍 Overall AI Review\n"
    body += f"{aggregated_data.get('overall_review', 'No overall review.')}\n\n"

    for cat in CATEGORIES:
        if cat == "overall_review":
            continue
        items = aggregated_data.get(cat, [])
        if items:
            cat_title = cat.replace("_", " ").title()
            body += f"### {cat_title}\n"
            for item in items:
                line_num = item.get("line", "?")
                comment_text = item.get("comment", "")
                body += f"- **Line {line_num}**: {comment_text}\n"
            body += "\n"

    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=GITHUB_HEADERS, json={"body": body})
        resp.raise_for_status()
        logger.info("Successfully posted AI review comment.")
    except requests.RequestException as e:
        logger.error(f"Error posting PR comment: {e}")

# -----------------------------------------------------
# Main Execution
# -----------------------------------------------------

def main() -> None:
    pr_number = get_latest_pr_number()
    if not pr_number:
        logger.info("No open PR found. Exiting...")
        return

    pr_branch = get_pr_branch(pr_number)
    if not pr_branch:
        logger.error("Cannot determine PR branch. Exiting...")
        return

    modified_files = get_modified_files(pr_number)
    if not modified_files:
        logger.info("No modified files in the PR. Exiting...")
        return

    # aggregator for final PR comment
    aggregated_data = {
        "overall_review": "Summary across all files.",
        "code_quality_and_best_practices": [],
        "readability_and_maintainability": [],
        "efficiency_and_performance_improvements": [],
        "security_vulnerabilities": []
    }

    for fobj in modified_files:
        file_path = fobj["filename"]
        content = get_file_content(file_path, pr_branch)
        if not content:
            continue

        ai_data = review_code(file_path, content)
        # gather inline comments from all categories except 'overall_review'
        inline_comments = []
        for cat in CATEGORIES:
            if cat == "overall_review":
                continue
            inline_comments.extend(ai_data.get(cat, []))

        # Post inline comments
        post_inline_comments(pr_number, file_path, inline_comments)

        # Merge overall_review
        aggregated_data["overall_review"] += f"\n{ai_data.get('overall_review', '')} (in {file_path})"
        # Merge categories
        for cat in CATEGORIES:
            if cat == "overall_review":
                continue
            aggregated_data[cat].extend(ai_data.get(cat, []))

    # Post final summarized PR comment
    post_pr_comment(pr_number, aggregated_data)

if __name__ == "__main__":
    main()
