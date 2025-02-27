import os
import requests
import openai
import base64
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# Ensure required environment variables are set
required_env_vars = {
    "PAT_TOKEN": GITHUB_TOKEN,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "REPO_NAME": REPO_NAME,
}
missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}. Ensure they are set in GitHub Secrets.")

# API Constants
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OPENAI_MODEL = "gpt-4o-mini"
AI_ROLE = "You are a professional software code reviewer. Always respond strictly in JSON format."


def get_latest_pr_number():
    """Fetch the most recent open PR number."""
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
    """Retrieve the branch name for a given PR number."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json().get("head", {}).get("ref")
    except requests.RequestException as e:
        logger.error(f"Error fetching PR branch: {e}")
        return None


def get_modified_files(pr_number):
    """Fetch the modified files in a PR."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching modified files: {e}")
        return []


def get_file_content(file_path, branch_name):
    """Retrieve the file content from a specific PR branch."""
    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
        response = requests.get(url, headers=GITHUB_HEADERS)
        response.raise_for_status()
        return base64.b64decode(response.json()["content"]).decode("utf-8")
    except requests.RequestException as e:
        logger.error(f"Error fetching file content for {file_path}: {e}")
        return None


def review_code(file_path, file_content):
    """Use OpenAI to review a file and return structured feedback."""
    language = file_path.split(".")[-1]
    prompt = f"""
    You are an AI code reviewer for {language}. Analyze the following file changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
    - Provide inline comments with line numbers and suggest improved code snippets.
    Additionally, generate an **overall review** summarizing the key findings.

    File Path: {file_path}
    Code:
    {file_content}

    Respond strictly in valid JSON format:
    {{
        "overall_review": "Summary of findings.",
        "code_quality_and_best_practices": [...],
        "readability_and_maintainability": [...],
        "efficiency_and_performance_improvements": [...],
        "security_vulnerabilities": [...]
    }}
    """

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": AI_ROLE}, {"role": "user", "content": prompt}]
        )
        ai_response = response.choices[0].message.content.strip()

        # Ensure JSON is properly formatted
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}")
        if json_start == -1 or json_end == -1:
            raise ValueError("AI response is not valid JSON.")

        return json.loads(ai_response[json_start : json_end + 1])

    except (Exception, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error reviewing code: {e}")
        return {
            "overall_review": "AI review could not be generated.",
            "code_quality_and_best_practices": [],
            "readability_and_maintainability": [],
            "efficiency_and_performance_improvements": [],
            "security_vulnerabilities": []
        }


def post_pr_comment(pr_number, review_data):
    """Post a summarized AI review as a PR comment."""
    formatted_review = "## 🔍 Overall AI Review\n"
    formatted_review += f"{review_data.get('overall_review', 'No overall review provided.')}\n\n"

    for category, comments in review_data.items():
        if category == "overall_review":
            continue
        formatted_review += f"### {category.replace('_', ' ').title()}\n"
        for comment in comments:
            formatted_review += f"- **Line {comment['line']}**: {comment['comment']}\n"
        formatted_review += "\n"

    try:
        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
        response = requests.post(url, headers=GITHUB_HEADERS, json={"body": formatted_review})
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error posting PR comment: {e}")


if __name__ == "__main__":
    PR_NUMBER = get_latest_pr_number()
    if PR_NUMBER:
        PR_BRANCH = get_pr_branch(PR_NUMBER)
        if PR_BRANCH:
            files = get_modified_files(PR_NUMBER)
            full_review_data = {"overall_review": "This PR contains changes that impact multiple areas."}

            for file in files:
                file_path = file["filename"]
                file_content = get_file_content(file_path, PR_BRANCH)
                if not file_content:
                    continue

                review_data = review_code(file_path, file_content)
                for category in ["code_quality_and_best_practices", "readability_and_maintainability",
                                 "efficiency_and_performance_improvements", "security_vulnerabilities"]:
                    full_review_data.setdefault(category, []).extend(review_data.get(category, []))

            post_pr_comment(PR_NUMBER, full_review_data)
