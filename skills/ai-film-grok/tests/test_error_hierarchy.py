"""Error-hierarchy unification tests (P2-1, senior-dev quality plan).

Subsystem gate/final errors must inherit ``FilmError`` so callers can catch all
pipeline errors with a single ``except FilmError``. ``FilmError`` is a
``RuntimeError`` subclass, so existing ``except RuntimeError`` / specific-error
handlers keep working (backward compatible).
"""

from __future__ import annotations

import importlib

import pytest

from util.errors import FilmError


def _load(name: str):
    return importlib.import_module(name)


@pytest.mark.parametrize(
    "module,cls",
    [
        ("production_gates", "ProductionGateError"),
        ("preflight", "PreflightError"),
        ("cinematic_gate", "CinematicGateError"),
        ("gate_auto", "GateAutoError"),
        ("continuity_programmatic", "ContinuityProgrammaticError"),
        ("narrative_rebind", "NarrativeRebindError"),
        ("delivery_artifact", "DeliveryArtifactError"),
        ("final.errors", "RenderError"),
        ("post.render_final_music", "RenderError"),
        # C5.2 hotpath RuntimeError → FilmError (still RuntimeError via FilmError)
        ("post.closeout", "CloseoutError"),
        ("media_queue", "QueueError"),
        ("input_fidelity", "InputFidelityError"),
        ("compose_render", "ComposeRenderError"),
        ("export_composition", "ComposeExportError"),
        ("h3_workflow", "H3WorkflowError"),
        ("h3_ship_native", "H3ShipNativeError"),
        ("media_qa", "MediaQAError"),
        ("render_workspace", "RenderWorkspaceError"),
    ],
)
def test_gate_errors_inherit_filmerror(module: str, cls: str) -> None:
    klass = getattr(_load(module), cls)
    assert issubclass(klass, FilmError)
    # Backward compatibility: still RuntimeError, so `except RuntimeError` holds.
    assert issubclass(klass, RuntimeError)


def test_render_timeout_transitively_filmerror() -> None:
    from final.errors import RenderTimeoutError

    assert issubclass(RenderTimeoutError, FilmError)


def test_filmerror_is_catch_all_for_gate_errors() -> None:
    from production_gates import ProductionGateError

    with pytest.raises(FilmError):
        raise ProductionGateError("boom")
