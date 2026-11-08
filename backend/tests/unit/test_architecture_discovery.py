"""An undiscovered namespace must never bypass the actual architecture gate."""

from pathlib import Path

import grimp


def test_architecture_graph_covers_every_runtime_python_module() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "studymate"
    files = tuple(root.rglob("*.py"))
    missing_markers = frozenset(
        source.parent.relative_to(root)
        for source in files
        if not (source.parent / "__init__.py").is_file()
    )
    assert not missing_markers, f"Runtime packages missing __init__.py: {missing_markers}"
    expected = frozenset(
        ".".join(("studymate", *source.relative_to(root).parts[:-1], source.stem))
        if source.name != "__init__.py"
        else ".".join(("studymate", *source.parent.relative_to(root).parts))
        for source in files
    )
    graph = grimp.build_graph("studymate", include_external_packages=True, cache_dir=None)
    missing = expected.difference(graph.modules)
    assert not missing, f"Architecture contracts did not discover runtime modules: {missing}"
