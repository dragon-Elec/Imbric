import os
import subprocess
from pathlib import Path
from ..daemon import PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("project", help="Show project information")
    p.add_argument("--deps", action="store_true", help="Show dependency tree")
    p.add_argument("--tasks", action="store_true", help="Show available Gradle tasks")

def _get_git_info() -> dict:
    """Get git information."""
    info = {"branch": "?", "commit": "?", "status": "?"}
    try:
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
        
        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()
        
        # Get status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                info["status"] = f"{len(lines)} changed file(s)"
            else:
                info["status"] = "clean"
    except Exception:
        pass
    return info

def _get_gradle_info() -> dict:
    """Get Gradle information."""
    info = {"version": "?", "kotlin": "?", "java": "?"}
    try:
        # Get Gradle version
        result = subprocess.run(
            ["./gradlew", "--version"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Gradle" in line and "version" in line:
                    info["version"] = line.split()[-1]
                    break
    except Exception:
        pass
    
    # Get Kotlin version from build.gradle.kts
    build_file = PROJECT_ROOT / "build.gradle.kts"
    if build_file.exists():
        try:
            content = build_file.read_text()
            import re
            # Look for kotlin version
            match = re.search(r"kotlin\(['\"](.+?)['\"]\)", content)
            if match:
                info["kotlin"] = match.group(1)
            # Look for java version
            match = re.search(r"JavaLanguageVersion\.of\((\d+)\)", content)
            if match:
                info["java"] = match.group(1)
        except Exception:
            pass
    
    return info

def _get_project_structure() -> dict:
    """Get project structure info."""
    info = {"modules": [], "source_files": 0, "test_files": 0}
    try:
        # Count source files
        src_dir = PROJECT_ROOT / "src" / "main" / "kotlin"
        if src_dir.exists():
            info["source_files"] = len(list(src_dir.rglob("*.kt")))
        
        # Count test files
        test_dir = PROJECT_ROOT / "src" / "test" / "kotlin"
        if test_dir.exists():
            info["test_files"] = len(list(test_dir.rglob("*.kt")))
        
        # Get modules from settings.gradle.kts
        settings_file = PROJECT_ROOT / "settings.gradle.kts"
        if settings_file.exists():
            content = settings_file.read_text()
            import re
            # Look for include statements
            matches = re.findall(r"include\(['\"](.+?)['\"]\)", content)
            info["modules"] = matches
    except Exception:
        pass
    return info

def run(args):
    print("=== Project Information ===")
    print()
    
    # Git info
    git = _get_git_info()
    print("Git:")
    print(f"  Branch: {git['branch']}")
    print(f"  Commit: {git['commit']}")
    print(f"  Status: {git['status']}")
    print()
    
    # Gradle info
    gradle = _get_gradle_info()
    print("Build:")
    print(f"  Gradle: {gradle['version']}")
    print(f"  Kotlin: {gradle['kotlin']}")
    print(f"  Java:   {gradle['java']}")
    print()
    
    # Project structure
    structure = _get_project_structure()
    print("Structure:")
    print(f"  Source files: {structure['source_files']}")
    print(f"  Test files:  {structure['test_files']}")
    if structure['modules']:
        print(f"  Modules:     {', '.join(structure['modules'])}")
    print()
    
    # Show dependency tree if requested
    if args.deps:
        print("Dependencies:")
        try:
            result = subprocess.run(
                ["./gradlew", "dependencies", "--configuration", "compileClasspath", "--console=plain"],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True
            )
            if result.returncode == 0:
                # Filter and format dependency tree
                for line in result.stdout.splitlines():
                    if line.strip() and not line.startswith("Root project"):
                        print(f"  {line}")
            else:
                print("  Could not fetch dependencies")
        except Exception:
            print("  Could not fetch dependencies")
        print()
    
    # Show available tasks if requested
    if args.tasks:
        print("Available Gradle tasks:")
        try:
            result = subprocess.run(
                ["./gradlew", "tasks", "--all", "--console=plain"],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True
            )
            if result.returncode == 0:
                # Filter and format tasks
                in_tasks_section = False
                for line in result.stdout.splitlines():
                    if "Tasks runnable from root project" in line:
                        in_tasks_section = True
                        continue
                    if in_tasks_section and line.strip():
                        if line.startswith("---"):
                            continue
                        print(f"  {line}")
            else:
                print("  Could not fetch tasks")
        except Exception:
            print("  Could not fetch tasks")
