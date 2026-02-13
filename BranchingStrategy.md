## Branching Strategy – GitHub Flow

We use **GitHub Flow**, a lightweight branching strategy suitable for small web projects and continuous delivery.

- `main` branch is always **deployable and stable**.
- Every new feature or bug fix is developed in a **separate feature branch** created from `main`.
- When the feature is ready, we create a **Pull Request (PR)** to merge the branch back into `main`.
- Code is reviewed, tested, and then merged. The feature branch is deleted after merge.

### Steps for a Typical Feature

1. Update local main:
   ```bash
   git checkout main
   git pull origin main
