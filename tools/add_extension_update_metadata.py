import json
import os
import shutil
import subprocess
import sys
import time
import tomllib


RELEASE_TIMESTAMP_KEY = "taiyo_updated_at"


def _git_executable(repo_root):
    local_git = os.path.join(repo_root, ".codex-tools", "MinGit", "cmd", "git.exe")
    if os.path.isfile(local_git):
        return local_git
    return shutil.which("git")


def _git_output(git_executable, repo_root, *args):
    if not git_executable:
        return ""
    try:
        result = subprocess.run(
            [git_executable, "-C", repo_root, *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _source_version(repo_root, package_id):
    manifest_path = os.path.join(
        repo_root,
        "_Taiyo_Blender_Extensions_Repo",
        package_id,
        "blender_manifest.toml",
    )
    try:
        with open(manifest_path, "rb") as handle:
            return tomllib.load(handle).get("version", "")
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def _package_timestamp(repo_root, package_id, package_version, archive_url, git_executable):
    relative_source = os.path.join("_Taiyo_Blender_Extensions_Repo", package_id)
    dirty = _git_output(
        git_executable,
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=normal",
        "--",
        relative_source,
    )
    if dirty and _source_version(repo_root, package_id) == package_version:
        return int(time.time())

    committed = _git_output(
        git_executable,
        repo_root,
        "log",
        "-1",
        "--format=%ct",
        "--",
        relative_source,
    )
    if committed.isdigit():
        return int(committed)

    archive_name = archive_url[2:] if archive_url.startswith("./") else ""
    archive_path = os.path.join(repo_root, "docs", "extensions", archive_name)
    try:
        return int(os.path.getmtime(archive_path))
    except OSError:
        return 0


def add_update_metadata(repo_root):
    index_path = os.path.join(repo_root, "docs", "extensions", "index.json")
    with open(index_path, "r", encoding="utf-8") as handle:
        index_data = json.load(handle)

    git_executable = _git_executable(repo_root)
    for item in index_data.get("data", ()):
        item[RELEASE_TIMESTAMP_KEY] = _package_timestamp(
            repo_root,
            item["id"],
            item.get("version", ""),
            item.get("archive_url", ""),
            git_executable,
        )

    with open(index_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(index_data, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    repo_root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(__file__), ".."))
    add_update_metadata(repo_root)
    print("Added extension update timestamps to docs/extensions/index.json")


if __name__ == "__main__":
    main()
