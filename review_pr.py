import os
import requests
import openai

# Load environment variables from GitHub Secrets
GITHUB_TOKEN = os.environ["PAT_TOKEN"]  # ✅ Corrected
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
REPO_NAME = os.environ["REPO_NAME"]

if not GITHUB_TOKEN:
    raise ValueError("❌ PAT_TOKEN environment variable is missing. Ensure it is set in GitHub Secrets.")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Step 1: Fetch the Latest Open PR Number
def get_latest_pr_number():
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls?state=open&sort=created&direction=desc"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        return response.json()[0]["number"]
    else:
        print("❌ No open PRs found or failed to fetch PRs.")
        return None

# Step 2: Fetch PR Files and Changes
def get_modified_files(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/files"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print("❌ Failed to fetch PR files:", response.json())
        return []
    
    return response.json()

# Step 3: Analyze Code Diff & Suggest Improvements
def analyze_code_diff(file_diffs):
    suggestions = []
    
    for file in file_diffs:
        filename = file["filename"]
        patch = file.get("patch", "")  # Code diff (line changes)
        
        if not patch:
            continue  # Skip files with no changes
        
        prompt = f"""
        You are an AI code reviewer. Analyze the following GitHub pull request code changes and provide feedback on:
        - Code quality and best practices
        - Readability and maintainability
        - Replacing nested if conditions with array mapping (if applicable)
        - Suggesting better code replacements where improvements are needed

        Code Diff (from {filename}):
        {patch}

        Provide inline comments with line numbers and replacement code (if needed).
        """

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional software code reviewer."},
                {"role": "user", "content": prompt}
            ]
        )

        suggestions.append({
            "filename": filename,
            "review": response.choices[0].message.content
        })

    return suggestions

# Step 4: Post Inline Comments on GitHub
def post_inline_comments(pr_number, review_suggestions):
    for suggestion in review_suggestions:
        filename = suggestion["filename"]
        review = suggestion["review"]

        # Extract inline comments with suggested code improvements
        comments = extract_inline_comments(review, filename)

        for comment in comments:
            comment_payload = {
                "body": comment["comment"],
                "commit_id": get_latest_commit_sha(pr_number),
                "path": filename,
                "side": "RIGHT",
                "line": comment["line_number"]
            }

            url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/comments"
            response = requests.post(url, headers=HEADERS, json=comment_payload)

            if response.status_code == 201:
                print(f"✅ Successfully posted inline comment on {filename}, line {comment['line_number']}")
            else:
                print(f"❌ Failed to post inline comment: {response.json()}")

# Step 5: Extract Inline Comments from AI Review
def extract_inline_comments(review_text, filename):
    inline_comments = []
    
    lines = review_text.split("\n")
    for line in lines:
        if "Line:" in line:
            parts = line.split("Line:")
            line_number = int(parts[1].split()[0])
            comment = " ".join(parts[1].split()[1:])
            
            inline_comments.append({
                "filename": filename,
                "line_number": line_number,
                "comment": comment
            })

    return inline_comments

# Step 6: Get Latest Commit SHA (Needed for Inline Comments)
def get_latest_commit_sha(pr_number):
    url = f"https://api.github.com/repos/{REPO_NAME}/pulls/{pr_number}/commits"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200 and response.json():
        return response.json()[-1]["sha"]  # Get latest commit SHA
    else:
        print("❌ Failed to fetch latest commit SHA.")
        return None

# Run AI Review Process
if __name__ == "__main__":
    print("📌 Fetching latest open PR number...")
    PR_NUMBER = get_latest_pr_number()
    
    if not PR_NUMBER:
        print("❌ No open PRs found. Exiting...")
        exit()

    print(f"🔍 Latest PR number: {PR_NUMBER}")
    
    print("📌 Fetching modified files...")
    files = get_modified_files(PR_NUMBER)
    
    if not files:
        print("❌ No modified files found. Exiting...")
        exit()

    print("📌 Analyzing code diffs...")
    review_suggestions = analyze_code_diff(files)

    print("📌 Posting inline comments...")
    post_inline_comments(PR_NUMBER, review_suggestions)
