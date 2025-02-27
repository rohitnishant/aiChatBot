import os
import requests
import openai
import base64
import json
import logging

# -----------------------------------------------------
# Global Constants & Configuration
# -----------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure required environment variables are set
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

REQUIRED_ENV_VARS = {
    "PAT_TOKEN": GITHUB_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "REPO_NAME": REPO_NAME,
}
missing_vars = [var for var, value in REQUIRED_ENV_VARS.items() if not value]
if missing_vars:
    raise ValueError(
        f"Missing environment variables: {', '.join(missing_vars)}. "
        "Ensure they are set in GitHub Secrets."
    )

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Set OpenAI credentials
openai.api_key = OPENAI_API_KEY

# Model & Prompt Role
OPENAI_MODEL = "gpt-4o-mini"
AI_SYSTEM_ROLE = (
    "You are a professional software code reviewer. "
    "Always respond strictly in JSON format."
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

def get_latest_pr_number() -> int | None:
    """
    Retrieve the latest open PR number for the repository.

    Returns:
        int | None: The latest PR number if found, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls"
        params = {"state": "open", "sort": "created", "direction": "desc"}
        response = requests.get(url, headers=GITHUB_HEADERS, params=params)
        response.raise_for_status()
        pull_requests = response.json()
        if pull_requests:
            return pull_requests[0]["number"]
        logger.info("No open PR found.")
    except requests.RequestException as e:
        logger.error(f"Error fetching latest PR number: {e}")
    return None


def get_pr_branch(pr_number: int) -> str | None:
    """
    Retrieve the branch name associated with a given PR number.

    Args:
        pr_number (int): Pull request number.

    Returns:
        str | None: The branch name if found, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json().get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
        return None


def get_modified_files(pr_number: int) -> list:
    """
    Fetch the modified files for a given PR.

    Args:
        pr_number (int): Pull request number.

    Returns:
        list: A list of file info objects from GitHub's API.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []


def get_file_content(file_path: str, branch_name: str) -> str | None:
    """
    Retrieve the content of a file from a specific branch.

    Args:
        file_path (str): The file path in the repo.
        branch_name (str): The branch from which to retrieve the file.

    Returns:
        str | None: The decoded file content if successful, otherwise None.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}"
        params = {"ref": branch_name}
        response = requests.get(url, headers=GITHUB_HEADERS, params=params)
        response.raise_for_status()
        content = response.json()["content"]
        return base64.b64decode(content).decode("utf-8")
    except requests.RequestException as e:
        logger.error(f"Error fetching file content for {file_path}: {e}")
        return None


def get_latest_commit_sha(pr_number: int) -> str | None:
    """
    Retrieve the latest commit SHA for a given PR.

    Args:
        pr_number (int): Pull request number.

    Returns:
        str | None: The latest commit SHA, or None if not found.
    """
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        commits = response.json()
        if commits:
            return commits[-1]["sha"]
    except requests.RequestException as e:
        logger.error(f"Error fetching latest commit SHA: {e}")
    return None


# -----------------------------------------------------
# OpenAI Review Functions
# -----------------------------------------------------

def review_code(file_path: str, file_content: str) -> dict:
    """
    Send file content to OpenAI for code review and return structured feedback.

    Args:
        file_path (str): Path of the file being reviewed.
        file_content (str): Full text content of the file.

    Returns:
        dict: Structured feedback from OpenAI with keys corresponding to categories.
    """
    language = file_path.split(".")[-1]
    # Request the AI to respond in strict JSON with specific categories
    prompt = f"""
    You are an AI code reviewer for {language}. Analyze the following file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    - Provide inline comments with line numbers and suggest improved code snippets.
    Additionally, generate an **overall_review** summarizing the key findings.

    File Path: {file_path}
    Code:
    {file_content}

    Respond strictly in valid JSON format like this:
    {{
      "overall_review": "Summary of the codebase or changes",
      "code_quality_and_best_practices": [
         {{"line": 10, "comment": "Refactor loop", "suggested_code": "..."}},
         ...
      ],
      "readability_and_maintainability": [...],
      "efficiency_and_performance_improvements": [...],
      "security_vulnerabilities": [...]
    }}
    """

    try:
        # Use openai's official library
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": AI_SYSTEM_ROLE},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        ai_response = response.choices[0].message.content.strip()

        # Parse the JSON from AI's response
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}")
        if json_start == -1 or json_end == -1:
            raise ValueError("AI did not return valid JSON.")

        data = json.loads(ai_response[json_start : json_end + 1])

        # Make sure each category is present; fallback to an empty list/string
        final_data = {}
        for cat in CATEGORIES:
            if cat == "overall_review":
                final_data[cat] = data.get(cat, "")
            else:
                final_data[cat] = data.get(cat, [])

        return final_data

    except (json.JSONDecodeError, ValueError, openai.error.OpenAIError) as e:
        logger.error(f"Error reviewing code for {file_path}: {e}")
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

def post_inline_comments(pr_number: int, file_path: str, comments: list):
    """
    Post inline comments to GitHub for the specified PR and file.

    Args:
        pr_number (int): Pull request number.
        file_path (str): File path in the repo.
        comments (list): List of comment objects from the AI.
    """
    commit_id = get_latest_commit_sha(pr_number)
    if not commit_id or not comments:
        return

    for comment in comments:
        line = comment.get("line")
        comment_text = comment.get("comment", "")
        if not line or not comment_text:
            continue  # Skip invalid comment

        payload = {
            "body": comment_text,
            "commit_id": commit_id,
            "path": file_path,
            "side": "RIGHT",
            "line": line
        }
        # Post each inline comment
        try:
            url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
            response = requests.post(url, headers=GITHUB_HEADERS, json=payload)
            response.raise_for_status()
            logger.info(f"Posted inline comment on {file_path}, line {line}")
        except requests.RequestException as e:
            logger.error(f"Error posting inline comment for {file_path}: {e}")


def post_pr_comment(pr_number: int, all_data: dict):
    """
    Post a summarized AI review as a single PR comment, including overall review and category feedback.

    Args:
        pr_number (int): Pull request number.
        all_data (dict): Aggregated AI feedback from multiple files.
    """
    # Start with an overall review
    overall = all_data.get("overall_review", "No overall review provided.")
    body = f"## 🔍 Overall AI Review\n{overall}\n\n"

    # Add category-specific items
    for cat in CATEGORIES:
        # Skip overall_review since we did it above
        if cat == "overall_review":
            continue
        if cat in all_data and all_data[cat]:
            nice_cat_name = cat.replace("_", " ").title()
            body += f"### {nice_cat_name}\n"
            for cobj in all_data[cat]:
                line = cobj.get("line", "N/A")
                comment_text = cobj.get("comment", "")
                body += f"- **Line {line}**: {comment_text}\n"
            body += "\n"

    # Post final PR comment
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
        response = requests.post(url, headers=GITHUB_HEADERS, json={"body": body})
        response.raise_for_status()
        logger.info("Successfully posted summarized AI review comment.")
    except requests.RequestException as e:
        logger.error(f"Error posting PR comment: {e}")


# -----------------------------------------------------
# Main Execution
# -----------------------------------------------------

if __name__ == "__main__":
    # 1. Find the latest PR number
    pr_num = get_latest_pr_number()
    if not pr_num:
        logger.info("No open PR found.")
        exit(0)

    # 2. Find the PR branch
    pr_branch = get_pr_branch(pr_num)
    if not pr_branch:
        logger.error("Cannot determine PR branch.")
        exit(0)

    # 3. Get modified files
    modified_files = get_modified_files(pr_num)
    if not modified_files:
        logger.info("No modified files in the PR.")
        exit(0)

    # 4. Initialize aggregated data
    aggregated_data = {
        "overall_review": "Summary across all files.",
        "code_quality_and_best_practices": [],
        "readability_and_maintainability": [],
        "efficiency_and_performance_improvements": [],
        "security_vulnerabilities": []
    }

    # 5. Review each file
    for fobj in modified_files:
        file_path = fobj["filename"]
        content = get_file_content(file_path, pr_branch)
        if not content:
            continue

        # AI review
        ai_data = review_code(file_path, content)
        # Post inline comments (sum all categories except overall_review)
        inline = []
        for cat in CATEGORIES:
            if cat == "overall_review":
                continue
            inline.extend(ai_data.get(cat, []))

        post_inline_comments(pr_num, file_path, inline)

        # Merge categories
        aggregated_data["overall_review"] += (
            "\n" + ai_data.get("overall_review", "") + f" (in {file_path})"
        )
        for cat in CATEGORIES:
            if cat == "overall_review":
                continue
            aggregated_data[cat].extend(ai_data.get(cat, []))

    # 6. Post final PR comment
    post_pr_comment(pr_num, aggregated_data)
