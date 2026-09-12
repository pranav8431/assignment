#!/usr/bin/env python3
"""
Builds and EXECUTES the notebooks in notebooks/ with a real Jupyter kernel.

Cells are defined in nb_discovery.py / nb_features.py, assembled with `nbformat`,
and executed by `nbclient` against the ipykernel in .venv. Every output committed
in the .ipynb is therefore produced by a genuine kernel run of the code above it --
nothing is transcribed by hand.

Run:  .venv/bin/python scripts/build_notebooks.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


def md(text):
    return new_markdown_cell(text.strip("\n"))


def code(src):
    return new_code_cell(src.strip("\n"))


def build(relpath, cells, timeout=600):
    nb = new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3 (capillary)",
                       "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": sys.version.split()[0]},
    })
    out = os.path.join(BASE, relpath)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # execute from the notebook's own directory, as Jupyter would
    client = NotebookClient(nb, timeout=timeout, kernel_name="python3",
                            resources={"metadata": {"path": os.path.dirname(out)}},
                            allow_errors=False)
    n_code = sum(1 for c in cells if c.cell_type == "code")
    try:
        client.execute()
        status = "OK"
    except CellExecutionError as e:
        status = f"CELL FAILED -- {str(e).splitlines()[-1][:120]}"

    # nbclient stamps per-cell wall-clock timings, and nbformat 4.5 assigns RANDOM
    # cell ids. Both must go, or two runs of identical code produce different files
    # and the pipeline's determinism guarantee is a lie.
    for i, c in enumerate(nb.cells):
        c.get("metadata", {}).pop("execution", None)
        c["id"] = f"cell-{i:03d}"
        # the kernel emits stdout as separate ZMQ messages that nbclient may or may
        # not coalesce depending on timing -- merge adjacent same-stream outputs so
        # the file does not change between identical runs
        merged = []
        for o in c.get("outputs", []):
            if (merged and o.get("output_type") == "stream"
                    and merged[-1].get("output_type") == "stream"
                    and merged[-1].get("name") == o.get("name")):
                merged[-1]["text"] = merged[-1]["text"] + o["text"]
            else:
                merged.append(o)
        if merged:
            c["outputs"] = merged
    nb.metadata.pop("widgets", None)

    nbformat.validate(nb)
    with open(out, "w") as f:
        nbformat.write(nb, f)

    n_out = sum(1 for c in nb.cells if c.cell_type == "code" and c.get("outputs"))
    n_img = sum(1 for c in nb.cells if c.cell_type == "code"
                for o in c.get("outputs", []) if "image/png" in o.get("data", {}))
    print(f"  {relpath:34s} {len(cells):>2} cells | {n_code} executed | "
          f"{n_out} with output | {n_img} figures  [{status}]")
    return status == "OK"


if __name__ == "__main__":
    import nb_discovery, nb_features
    print("Building notebooks (real ipykernel execution via nbclient):")
    ok  = build("notebooks/00_discovery.ipynb", nb_discovery.cells())
    ok &= build("notebooks/01_feature_build.ipynb", nb_features.cells())
    sys.exit(0 if ok else 1)
