#!/usr/bin/env python3
"""Synchronise repository status, graph documentation, and install guidance.

Generated README sections are deliberately small and marker-bounded so that
maintainer prose outside those sections remains human-owned.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN GENERATED: {name} -->"
END = "<!-- END GENERATED: {name} -->"


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def replace_block(path: Path, name: str, content: str) -> None:
    start = BEGIN.format(name=name)
    stop = END.format(name=name)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    block = f"{start}\n{content.rstrip()}\n{stop}"
    if start in text and stop in text:
        before, remainder = text.split(start, 1)
        _, after = remainder.split(stop, 1)
        updated = before + block + after
    else:
        updated = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(updated, encoding="utf-8")


def replace_text(text: str, name: str, content: str) -> str:
    start = BEGIN.format(name=name)
    stop = END.format(name=name)
    block = f"{start}\n{content.rstrip()}\n{stop}"
    if start in text and stop in text:
        before, remainder = text.split(start, 1)
        _, after = remainder.split(stop, 1)
        return before + block + after
    return text.rstrip() + "\n\n" + block + "\n"


def with_block(path: Path, name: str, content: str) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return replace_text(text, name, content)


def project_data() -> dict[str, object]:
    plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    registry = json.loads(
        (ROOT / "skills/ai-film-grok/registry/skills.json").read_text(encoding="utf-8")
    )
    shipped_skill_dirs = sorted(
        path for path in (ROOT / "skills").iterdir() if (path / "SKILL.md").is_file()
    )
    scripts = sorted(
        path.relative_to(ROOT).as_posix()
        for skill_dir in shipped_skill_dirs
        for path in (skill_dir / "scripts").rglob("*.py")
    )
    tests = sorted(
        path.relative_to(ROOT).as_posix()
        for test_root in [
            *(skill_dir / "tests" for skill_dir in shipped_skill_dirs),
            ROOT / "tests",
        ]
        if test_root.is_dir()
        for path in test_root.rglob("test_*.py")
    )
    return {
        "name": plugin["name"],
        "version": plugin["version"],
        "skills": registry.get("skills", []),
        "shipped_skills": [path.name for path in shipped_skill_dirs],
        "scripts": scripts,
        "tests": tests,
    }


def status_block(data: dict[str, object]) -> str:
    skills = data["skills"]
    assert isinstance(skills, list)
    implemented = sum(1 for item in skills if item.get("status") == "implemented")
    return "\n".join(
        [
            "### 当前项目状态（自动同步）",
            "",
            f"- 插件版本：`{data['version']}`",
            f"- Published skills：`{len(data['shipped_skills'])}`",
            f"- Skill Registry：`{implemented}/{len(skills)}` 项标记为 `implemented`",
            f"- Python 脚本：`{len(data['scripts'])}` 个",
            f"- pytest 文件：`{len(data['tests'])}` 个",
            "- 同步入口：`make sync-docs`（只更新文档）或 `make sync`（验证、提交并 push）",
            "- Graph：[`docs/GRAPH.md`](./docs/GRAPH.md)",
        ]
    )


def install_block() -> str:
    return "\n".join(
        [
            "### 文档与远端同步（维护者）",
            "",
            "代码或插件结构变更后，在仓库根目录执行：",
            "",
            "```bash",
            "make audit       # 只读审计 + fast tests + 更新 baseline",
            "make coverage    # 生成 coverage.json 并检查 baseline 门槛",
            "make sync-docs   # 生成 Graph、状态摘要与安装说明",
            "make release-check",
            "make sync        # 验证通过后提交、push，并核对 origin SHA",
            "```",
            "",
            "首次启用本地 push 门禁：",
            "",
            "```bash",
            "make install-hooks",
            "```",
            "",
            "同步器不会提交 `.env`、`config.env`、`.codegraph`、`.omo`、`.kilo` 或备份目录。",
        ]
    )


def graph_markdown(data: dict[str, object]) -> str:
    skills = data["skills"]
    assert isinstance(skills, list)
    by_phase: dict[str, list[str]] = {}
    for item in skills:
        for phase in item.get("phases", ["?"]):
            by_phase.setdefault(str(phase), []).append(str(item["id"]))
    phase_lines = [
        f"| Phase {phase} | {', '.join(sorted(ids))} |"
        for phase, ids in sorted(by_phase.items())
    ]
    test_lines = "\n".join(f"- `{name}`" for name in data["tests"])
    return "\n".join(
        [
            "# Project Graph",
            "",
            "> This file is generated by `scripts/sync_project_docs.py`. Edit the source files, then run `make sync-docs`.",
            "",
            f"- Plugin: `{data['name']}` v`{data['version']}`",
            f"- Shipped skills: {', '.join(f'`{name}`' for name in data['shipped_skills'])}.",
            "- Source of truth: `plugin.json`, shipped `skills/*/`, registry, scripts, and tests.",
            "- Local `.codegraph` is an ignored machine cache and is intentionally not published.",
            "",
            "```mermaid",
            "flowchart TD",
            '    A["Prompt / Script"] --> B["Plan + Drama Graph"]',
            '    B --> C["Asset + State Registry"]',
            '    C --> D["Media Queue / I2V"]',
            '    D --> E["Audio + Post"]',
            '    E --> F["QA Gates + Delivery"]',
            '    G["Skill Registry"] -. routes .-> B',
            "    G -. capabilities .-> D",
            "```",
            "",
            "## Registry by phase",
            "",
            "| Phase | Registered skills |",
            "|---|---|",
            *phase_lines,
            "",
            "## Repository surfaces",
            "",
            "| Surface | Role |",
            "|---|---|",
            "| `skills/ai-film-grok/scripts/aifilm` | CLI launcher |",
            "| `skills/ai-film-grok/registry/skills.json` | Capability and routing registry |",
            "| `skills/ai-film-grok/tests/` | Automated gates |",
            "| `skills/ai-film-project/` | Project blueprint skill and validator |",
            "| `tests/` | Plugin-level contract tests |",
            "| `README.md` | User and maintainer installation |",
            "| `.github/workflows/ci.yml` | CI validation |",
            "",
            "## Test inventory",
            "",
            test_lines,
            "",
            "## Update contract",
            "",
            "1. Change source code or registry.",
            "2. Run `make sync-docs`.",
            "3. Run `make release-check`.",
            "4. Run `make sync` to commit, push, and verify local/remote SHA equality.",
        ]
    )


def generate() -> None:
    data = project_data()
    replace_block(ROOT / "README.md", "project-status", status_block(data))
    replace_block(ROOT / "README.md", "maintainer-install", install_block())
    replace_block(
        ROOT / "skills/ai-film-grok/README.md", "project-status", status_block(data)
    )
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/GRAPH.md").write_text(graph_markdown(data) + "\n", encoding="utf-8")


def generated_files() -> dict[Path, str]:
    data = project_data()
    return {
        ROOT / "README.md": replace_text(
            with_block(ROOT / "README.md", "project-status", status_block(data)),
            "maintainer-install",
            install_block(),
        ),
        ROOT / "skills/ai-film-grok/README.md": with_block(
            ROOT / "skills/ai-film-grok/README.md", "project-status", status_block(data)
        ),
        ROOT / "docs/GRAPH.md": graph_markdown(data) + "\n",
    }


def generated_docs_are_current() -> bool:
    return all(
        path.exists() and path.read_text(encoding="utf-8") == content
        for path, content in generated_files().items()
    )


def git_status() -> list[str]:
    output = run("git", "status", "--porcelain")
    return output.splitlines() if output else []


def check_clean_for_sync() -> None:
    ignored = (".codegraph", ".omo/", ".kilo/", "backups-skills/")
    allowed_untracked = (
        ".githooks/",
        "docs/GRAPH.md",
        "scripts/",
        "skills/ai-film-grok/scripts/",
        "skills/ai-film-grok/tests/",
    )
    unexpected = []
    for line in git_status():
        path = line[3:]
        if line.startswith("?? ") and not any(
            path.startswith(prefix) for prefix in allowed_untracked + ignored
        ):
            unexpected.append(line)
    if unexpected:
        print("同步前发现未提交改动；请先确认这些改动属于本次发布：", file=sys.stderr)
        print("\n".join(unexpected), file=sys.stderr)
        raise SystemExit(2)


def commit_and_push() -> None:
    check_clean_for_sync()
    run("git", "add", "-u")
    run(
        "git",
        "add",
        "scripts/sync_project_docs.py",
        ".githooks/pre-push",
        "docs/GRAPH.md",
        "skills/ai-film-grok/scripts",
        "skills/ai-film-grok/tests",
    )
    run("git", "diff", "--cached", "--check")
    if (
        subprocess.run(
            ("git", "diff", "--cached", "--quiet"), cwd=ROOT, check=False
        ).returncode
        == 0
    ):
        print("没有可提交的变更。")
        return
    branch = run("git", "branch", "--show-current")
    run("git", "commit", "-m", "chore: sync project sources and documentation")
    run("git", "push", "origin", branch)
    run("git", "fetch", "origin", branch)
    local = run("git", "rev-parse", "HEAD")
    remote = run("git", "rev-parse", f"origin/{branch}")
    if local != remote:
        raise SystemExit(f"remote SHA mismatch: local={local} origin/{branch}={remote}")
    print(f"同步完成：{branch} {local}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="只检查生成结果是否已是最新"
    )
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not generated_docs_are_current():
            print("文档已过期；请运行 make sync-docs。", file=sys.stderr)
            return 1
        return 0
    generate()
    if args.commit or args.push:
        commit_and_push()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
