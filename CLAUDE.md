## Git Conventions
- Always use conventional commit messages referencing GitHub issue numbers (e.g., `fix(auth): resolve login race condition`). If I give an issue number, put it in the footer of a commit. Never commit without an issue reference when one is provided. Do not credit Claude or any other LLM or, in fact, anybody.
- After making code edits, always run the pre-commit hooks or linter (e.g., `ruff check`, `pre-commit run`) BEFORE staging and committing. If a hook fails, fix the issue and re-stage before committing again.
## Frontend / CSS for web projects
- When making CSS changes, especially for responsive/mobile layouts, always check for specificity conflicts and test that changes don't cause regressions in other viewport sizes or related components. Prefer targeted selectors over broad resets like `all:unset`.
## Editing Rules
- Before editing a file that was just modified, always re-read it first to get the current content. Never assume file contents are unchanged after a prior edit in the same session.
- When exploring directories or looking for files, use `ls` or `find` to list contents first rather than probing individual files one by one. Minimize unnecessary tool calls.
## Debugging
- When debugging, check CSS/display issues before diving into PHP/Python query logic. The root cause may be a styling rule (e.g., `.hidden { display: none }`) rather than a data/query problem.
## Test-driven development
- When exploring a new codebase, run the tests first.
- Always use a red/green test pattern. Write tests, run them first, and MAKE SURE THEY FAIL, first. Then write the code that makes the tests pass. These should all be self-contained unit tests that mock any external depedencies and thoroughly exercise the codebase.
## Github Actions and Auto-Versioning
- If it doesn't exist, add a file in .github/workflows/version-release.yml that contains this code:
    name: Bump version
    on:
      push:
        branches:
          - main
    jobs:
      bump-version:
        if: "!startsWith(github.event.head_commit.message, 'bump:')"
        runs-on: ubuntu-latest
        name: "Bump version and create changelog with commitizen"
        steps:
          - name: Check out
            uses: actions/checkout@v6
            with:
              fetch-depth: 0
              ssh-key: "${{ secrets.COMMIT_KEY }}"
          - name: Create bump and changelog
            uses: commitizen-tools/commitizen-action@master
            with:
              push: false
          - name: Push using ssh
            run: |
              git push origin main --tags
This will ensure that the version is updated.
- Ensure that there is a .pyproject.toml file in the root of the project. It should contain, at a minimum (and where {{ }} indicate variables):
    [project]
    name = "{{ PROJECT_NAME }}"
    version = "1.0.0"
    description = "{{ PROJECT_DESCRIPTION }}"
    readme = "README.md"
    requires-python = ">=3.12"
    [tool.commitizen]
    version = "1.0.0"
    version_files = [
        "__version__.py",
        "pyproject.toml:version"
    ]
    update_changelog_on_bump = true
## Packages
- You should use uv for packaging and running
## Web Development
- When doing web development work, you should use the Puppeteer MCP server to check what the output looks like in a browser using the screenshot tool.
- Sometimes, if this is a Django project for example, it will involve visiting localhost on port 443 with SSL, but the SSL certificates will be self signed, so this has to be handled. You should determine how to visit the page in question and whether it needs a connection to the server on localhost or whether it can be viewed in the browser as a file, or served with python -m http.server.
- If you are running in a Django project, you should always connect using a server and never as a local file in the browser or using Python's built-in server. This is because there may be templates and contexts that need rendering.
- Before you work out whether or not you need to serve the files yourself, try connecting to localhost on 443 with SSL and SSL self-signed certificate bypasses. This might just work.
## Github
- When asked to create a pull request on GitHub using the gh tool, never attribute Claude.
- Branch names should be of the format: feature/description-of-branch-{issue number} (where {issue number} is a Github issue number that corresponds to the work in progress). So, for example, we might have feature/new-menu-items-245. If the problem is a bug then the branch should be bug/description-of-branch-{issue number}
- The workflow that we use is to branch off main into a branch named as above. We then make the fixes and make everything work and write the features, etc. We then commit the changes, rebase from main, and then issue a pull request to GitHub using gh. You should not issue pull requests automatically, but only when asked by the user. This is because we often have multiple commits that go into a pull request.
