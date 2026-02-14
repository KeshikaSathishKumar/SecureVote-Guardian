# GitHub Flow Branching Strategy

## Overview

We follow **GitHub Flow**, a lightweight branching strategy well suited for small web projects and continuous development.

### Key Principles

* The `main` branch is **always stable, clean, and deployable**.
* Every new feature, enhancement, or bug fix is developed in a **separate feature branch** created from `main`.
* Once development is complete, changes are integrated using a **Pull Request (PR)**.
* Code is **reviewed and tested** before merging into `main`.
* Feature branches are **deleted** after a successful merge.

This strategy keeps the main codebase stable while allowing parallel development.

---

## Typical Feature Development Workflow

### 1. Update Local Main Branch

Before starting any new work, ensure your local `main` branch is up to date:

```bash
git checkout main
git pull origin main
```

### 2. Create a Feature Branch

Create a new branch for your feature with a descriptive name:

```bash
git checkout -b feature/frontend-voting-form
```

**Naming Convention:**
- `feature/description` - for new features
- `bugfix/description` - for bug fixes
- `hotfix/description` - for critical production fixes

Feature branches use descriptive naming for clarity.

### 3. Commit Changes

Make your changes and commit them with clear, descriptive messages:

```bash
git add .
git commit -m "Add basic voting form UI"
```

**Commit Message Best Practices:**
- Use present tense ("Add" not "Added")
- Be descriptive but concise
- Reference issue numbers if applicable

### 4. Push Branch to GitHub

Push your feature branch to the remote repository:

```bash
git push -u origin feature/frontend-voting-form
```

> **Note:** Using `-u` sets the upstream branch, making future pushes easier. After the first push, you can simply use `git push`.

### 5. Create Pull Request

A Pull Request is opened on GitHub:

* **Base branch:** `main`
* **Compare branch:** `feature/frontend-voting-form`

The PR enables:
- Code review by team members
- Discussion and feedback
- Automated testing validation
- Documentation of changes

**PR Template:**
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Enhancement

## Testing
- [ ] All tests pass
- [ ] Manual testing completed
```

### 6. Merge & Cleanup

After review and successful testing:

1. **Merge the Pull Request** on GitHub
2. **Delete the feature branch** (both locally and remotely)

```bash
# Delete local branch
git branch -d feature/frontend-voting-form

# Delete remote branch (if not done via GitHub)
git push origin --delete feature/frontend-voting-form
```

---

## Benefits of GitHub Flow

| Benefit | Description |
|---------|-------------|
| ✅ **Stable Main Branch** | Main branch is always deployable and production-ready |
| ✅ **Parallel Development** | Multiple features can be developed simultaneously |
| ✅ **Safe Integration** | Changes are reviewed before merging |
| ✅ **Code Review Culture** | Encourages collaboration and knowledge sharing |
| ✅ **Reduced Risk** | Prevents breaking production code |
| ✅ **Clear History** | Easy to track what changes were made and when |

---

## Feature Branch Demonstration Example

### Example: Adding Project Structure

This example demonstrates a complete workflow for adding the initial project structure:

#### Step 1: Prepare
```bash
git checkout main
git pull origin main
git checkout -b feature/project-structure
```

#### Step 2: Make Changes
```bash
# Create project structure
mkdir -p src/backend src/frontend
touch README.md .gitignore requirements.txt

# Add content to files
# ... (make your changes)
```

#### Step 3: Commit and Push
```bash
git add .
git commit -m "Add initial Flask project structure and .gitignore"
git push -u origin feature/project-structure
```

#### Step 4: Create Pull Request
1. Go to GitHub repository
2. Click "Compare & pull request"
3. Fill in PR details:
   - **Title:** Add initial Flask project structure
   - **Description:** 
     ```
     - Created basic folder structure (src/backend, src/frontend)
     - Added .gitignore for Python/Flask projects
     - Added requirements.txt with initial dependencies
     - Created README.md with project overview
     ```
4. Click "Create pull request"

#### Step 5: Review and Merge
1. Wait for code review (if working in a team)
2. Ensure all checks pass
3. Click "Merge pull request"
4. Click "Delete branch"

#### Step 6: Update Local Repository
```bash
git checkout main
git pull origin main
git branch -d feature/project-structure
```

---

## Common Scenarios

### Scenario 1: Multiple Commits on Feature Branch

```bash
# Make first change
git add .
git commit -m "Add voting form template"
git push

# Make second change
git add .
git commit -m "Add form validation logic"
git push

# Make third change
git add .
git commit -m "Add styling to voting form"
git push
```

All commits will be included in the same Pull Request.

### Scenario 2: Keeping Feature Branch Updated

If `main` has changed while you're working on your feature:

```bash
# From your feature branch
git checkout feature/your-feature
git fetch origin
git merge origin/main

# Or use rebase (cleaner history)
git rebase origin/main
```

### Scenario 3: Working on Multiple Features

```bash
# Create and work on feature A
git checkout -b feature/voting-system
# ... make changes ...
git push -u origin feature/voting-system

# Switch to main and create feature B
git checkout main
git checkout -b feature/results-dashboard
# ... make changes ...
git push -u origin feature/results-dashboard
```

---

## Best Practices

### ✅ DO:
- Keep feature branches small and focused
- Commit frequently with clear messages
- Pull from `main` regularly to avoid conflicts
- Delete branches after merging
- Write descriptive PR descriptions
- Respond to code review feedback promptly

### ❌ DON'T:
- Commit directly to `main`
- Leave feature branches open for too long
- Include multiple unrelated features in one branch
- Force push to shared branches
- Ignore code review comments
- Merge without testing

---

## Quick Reference

### Essential Commands

```bash
# Start new feature
git checkout main
git pull origin main
git checkout -b feature/feature-name

# Work on feature
git add .
git commit -m "Descriptive message"
git push -u origin feature/feature-name

# Update feature branch with latest main
git checkout feature/feature-name
git merge origin/main

# After PR is merged
git checkout main
git pull origin main
git branch -d feature/feature-name
```

---

## Troubleshooting

### Problem: Can't switch branches (uncommitted changes)

**Solution:**
```bash
# Option 1: Commit changes
git add .
git commit -m "WIP: Save current progress"

# Option 2: Stash changes
git stash
git checkout main
git stash pop
```

### Problem: Merge conflicts

**Solution:**
```bash
# Update your branch with main
git checkout feature/your-feature
git merge origin/main

# Git will mark conflicts in files
# Open files, resolve conflicts manually
# Look for <<<<<<< HEAD markers

git add .
git commit -m "Resolve merge conflicts"
git push
```

### Problem: Accidentally committed to main

**Solution:**
```bash
# Create branch from current state
git branch feature/accidental-work

# Reset main to remote state
git checkout main
git reset --hard origin/main

# Switch to feature branch
git checkout feature/accidental-work
git push -u origin feature/accidental-work
```
