import os
import requests
import openai

# Environment Variables
GITHUB_TOKEN = os.getenv("PAT_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("❌ PAT_TOKEN environment variable is missing. Ensure it is set in GitHub Secrets.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_NAME = os.getenv("REPO_NAME")

# GitHub API Headers
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Constants
GITHUB_API_BASE_URL = "https://api.github.com"
OPENAI_MODEL = "gpt-4"

def get_latest_pr_number():
    """
    Fetch the latest open PR number from the repository.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        latest_pr = response.json()[0]
        return latest_pr["number"]
    else:
        print("No open PRs found or failed to fetch PRs.")
        return None

<<<<<<< Updated upstream
# Step 2: Fetch PR Files
=======
def get_pr_branch(pr_number):
    """
    Fetch the branch name of the given PR number.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json()["head"]["ref"]
    else:
        print(f"❌ Failed to fetch PR branch: {response.json()}")
        return None

>>>>>>> Stashed changes
def get_modified_files(pr_number):
    """
    Fetch the list of modified files in the given PR number.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print("Failed to fetch PR files:", response.json())
        return []
    
    return response.json()

<<<<<<< Updated upstream
# Step 3: Extract Code Diff
def get_code_diff(files):
    diffs = []
    for file in files:
        filename = file["filename"]
        patch = file.get("patch", "")  # Patch contains code diff
        diffs.append(f"File: {filename}\nDiff:\n{patch}\n\n")
=======
def get_file_content(file_path, branch_name):
    """
    Fetch the content of a file from the given branch.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    response = requests.get(url, headers=HEADERS)
>>>>>>> Stashed changes
    
    return "\n".join(diffs)

<<<<<<< Updated upstream
# Step 4: Call ChatGPT API for Code Review
def review_code_with_chatgpt(code_diff):
=======
    return None

def review_code(file_path, file_content):
    """
    Call the OpenAI API to review the code and provide feedback.
    """
    language = file_path.split(".")[-1]
    
>>>>>>> Stashed changes
    prompt = f"""
    You are an AI code reviewer. Analyze the following GitHub pull request code changes and provide feedback on:
    - Code quality and best practices
    - Readability and maintainability
    - Efficiency and performance improvements
    - Security vulnerabilities (if any)
<<<<<<< Updated upstream
=======
    - Provide inline comments with line numbers and suggest improved code snippets.

    File Path: {file_path}
    Code:
    {file_content}

    Respond strictly in valid JSON format:
    {{
        "review": "Overall review text here.",
        "comments": [
            {{"line": 12, "comment": "Consider refactoring this loop to use a dictionary lookup instead of multiple if conditions.", "suggested_code": "new_code_here"}},
            {{"line": 25, "comment": "Avoid hardcoding API keys. Use environment variables instead.", "suggested_code": "new_code_here"}}
        ]
    }}
    """
>>>>>>> Stashed changes
    
    Code Diff:
    {code_diff}
    
    Provide a structured review with clear and constructive comments.
    """

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # New SDK format

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional software code reviewer."},
            {"role": "user", "content": prompt}
        ]
    )

<<<<<<< Updated upstream
    return response.choices[0].message.content

# Step 5: Post AI Review as PR Comment
=======
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

def post_inline_comments(pr_number, file_path, comments):
    """
    Post inline comments on the PR for the given file.
    """
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
            "line": comment["line"]
        }

        url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/comments"
        response = requests.post(url, headers=HEADERS, json=comment_payload)

        if response.status_code == 201:
            print(f"✅ Successfully posted inline comment on {file_path}, line {comment['line']}")
        else:
            print(f"❌ Failed to post inline comment: {response.json()}")

>>>>>>> Stashed changes
def post_pr_comment(pr_number, review):
    """
    Post the overall AI review as a comment on the PR.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/issues/{pr_number}/comments"
    data = {"body": review}
    
    response = requests.post(url, headers=HEADERS, json=data)
    
    if response.status_code == 201:
        print("Successfully posted AI review comment.")
    else:
<<<<<<< Updated upstream
        print("Failed to post PR comment:", response.json())
=======
        print(f"❌ Failed to post PR comment: {response.json()}")

def get_latest_commit_sha(pr_number):
    """
    Fetch the latest commit SHA for the given PR number.
    """
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        return response.json()[-1]["sha"]
    else:
        print("❌ Failed to fetch latest commit SHA.")
        return None
>>>>>>> Stashed changes

if __name__ == "__main__":
    print("Fetching latest open PR number...")
    PR_NUMBER = get_latest_pr_number()
    
    if not PR_NUMBER:
        print("No open PRs found. Exiting...")
        exit()

    print(f"Latest PR number: {PR_NUMBER}")
    
    print("Fetching modified files...")
    files = get_modified_files(PR_NUMBER)
    
    if not files:
        print("No modified files found. Exiting...")
        exit()

    print("Extracting code diffs...")
    code_diff = get_code_diff(files)

    print("Reviewing code with ChatGPT...")
    ai_review = review_code_with_chatgpt(code_diff)

    print("Posting AI review as a PR comment...")
    post_pr_comment(PR_NUMBER, ai_review)
