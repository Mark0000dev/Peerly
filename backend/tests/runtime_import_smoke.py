"""Import the runtime tree with development-only import roots denied."""

import importlib
import importlib.abc
import importlib.machinery
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

DEV_ROOTS = frozenset(
    {
        "types_aiobotocore",
        "types_aiobotocore_s3",
        "types_authlib",
        "pytest",
        "mypy",
        "ruff",
    }
)


class NoDevelopmentImports(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: Sequence[str] | None = None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if fullname.split(".", 1)[0] in DEV_ROOTS:
            raise ModuleNotFoundError("Runtime imported a development-only package", name=fullname)
        return None


def main() -> None:
    source = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(source))
    sys.meta_path.insert(0, NoDevelopmentImports())
    modules: set[str] = set()
    for file in (source / "studymate").rglob("*.py"):
        parts = file.relative_to(source).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.add(".".join(parts))
    imported = tuple(sorted(modules))
    for name in imported:
        importlib.import_module(name)
    if any(name.split(".", 1)[0] in DEV_ROOTS for name in sys.modules):
        raise AssertionError("Runtime loaded development-only imports")
    sys.stdout.write(
        f"Runtime imports accepted: {len(imported)} modules; development imports denied\n"
    )


if __name__ == "__main__":
    main()
