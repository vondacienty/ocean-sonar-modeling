"""Vessel attitude correction of single-beam soundings.

Each observation ``(x, y, d, roll, pitch, heave)`` gives the beam
offsets ``x``/``y`` and the measured depth ``d`` (metres, ``d >= 0``)
together with the vessel ``roll``/``pitch`` (degrees) and ``heave``
(metres, positive up) at sounding time. The corrected position applies
the roll rotation about the x axis followed by the pitch rotation about
the y axis, then subtracts heave from the resulting depth.
"""

from __future__ import annotations

import json
import math

from .svp import _is_real_number

__all__ = ["correct", "batch"]

_FIELDS = ("x", "y", "d", "roll", "pitch", "heave")


def correct(observations):
    """Apply vessel attitude to sounding observations.

    ``observations`` is a non-empty list/tuple whose items are
    six-element lists/tuples ``(x, y, d, roll, pitch, heave)``. Every
    value must be a finite non-bool int/float and ``d`` must be
    ``>= 0``; lengths are in metres, angles in degrees and heave is
    positive up. With ``r``/``p`` the roll/pitch in radians and
    ``cr``/``sr``/``cp``/``sp`` their cosines/sines, each item is
    corrected by rotating first about the x axis, then the y axis::

        X = cp * x + sp * (sr * y + cr * d)
        Y = cr * y - sr * d
        D = -sp * x + cp * (sr * y + cr * d) - heave

    Validation order (first error wins): the outer container, its
    non-emptiness, then per observation the item container, its length
    and the fields ``x``, ``y``, ``d``, ``roll``, ``pitch``, ``heave``
    in that order. Container and value type errors raise ``TypeError``;
    an empty container, a non-six-element item, a non-finite value or
    ``d < 0`` raise ``ValueError``. Item error messages are prefixed
    with ``"observation[i]: "``.

    Returns a tuple in observation order of ``(X, Y, D)`` triples of
    floats, each rounded to 6 decimals (negative zero normalized to
    ``0.0``). Inputs are not modified.
    """
    if not isinstance(observations, (list, tuple)):
        raise TypeError("observations must be a list or tuple")
    if len(observations) == 0:
        raise ValueError("observations must be non-empty")

    results = []
    for i in range(len(observations)):
        obs = observations[i]
        prefix = f"observation[{i}]: "
        if not isinstance(obs, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(obs) != 6:
            raise ValueError(prefix + "must have 6 elements")
        values = []
        for name, value in zip(_FIELDS, obs):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
            if name == "d" and not value >= 0:
                raise ValueError(prefix + "d must be >= 0")
            values.append(value)

        x, y, d, roll, pitch, heave = values
        r = math.radians(roll)
        p = math.radians(pitch)
        cr, sr = math.cos(r), math.sin(r)
        cp, sp = math.cos(p), math.sin(p)
        result = []
        for v in (
            cp * x + sp * (sr * y + cr * d),
            cr * y - sr * d,
            -sp * x + cp * (sr * y + cr * d) - heave,
        ):
            v = round(float(v), 6)
            result.append(0.0 if v == 0 else v)
        results.append(tuple(result))
    return tuple(results)


def batch(observations, limit=1.0) -> bytes:
    """Correct a batch of attitude observations and serialize as JSON bytes.

    Calls :func:`correct` exactly once with ``observations`` — its
    validation and exceptions apply unchanged and the input is not
    modified. ``limit`` is validated after the correction: it must be a
    non-bool int/float with ``limit >= 0``; finiteness is checked for
    floats only, so an arbitrarily large non-negative int is accepted.
    A bool or non-number raises ``TypeError``; a non-finite float or a
    negative value raises ``ValueError``.

    With ``R`` the tuple returned by :func:`correct`, each observation
    ``i`` yields the depth adjustment
    ``a = round(float(R[i][2] - observations[i][2]), 6)`` (negative
    zero normalized to ``0.0``) and the flag ``w = abs(a) <= limit``.

    The returned document has top-level keys exactly in the order
    ``results, summary``: ``results`` is an array in observation order
    of ``[X, Y, D, a, w]`` arrays, with ``X``, ``Y`` and ``D`` taken
    directly from ``R[i]``; ``summary`` has keys exactly in the order
    ``count, pass_count, max_abs_adjustment, quality`` where ``count``
    and ``pass_count`` are ints, ``max_abs_adjustment`` is
    ``round(float(max(abs(a))), 6)`` and ``quality`` is ``"pass"`` only
    when every ``w`` is true, otherwise ``"fail"``.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``serialize_trend``. Floats are
    first rounded with ``round(float(v), 6)`` and negative zero is
    normalized to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    corrected = correct(observations)

    if not _is_real_number(limit):
        raise TypeError("limit must be a non-bool int or float")
    if type(limit) is float and not math.isfinite(limit):
        raise ValueError("limit must be finite")
    if not limit >= 0:
        raise ValueError("limit must be >= 0")

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    adjustments = [
        rounded_float(corrected[i][2] - observations[i][2])
        for i in range(len(corrected))
    ]
    within = [abs(a) <= limit for a in adjustments]

    count = int(len(corrected))
    pass_count = int(sum(1 for w in within if w))
    max_abs_adjustment = rounded_float(max(abs(a) for a in adjustments))
    document = {
        "results": [
            [
                corrected[i][0],
                corrected[i][1],
                corrected[i][2],
                adjustments[i],
                within[i],
            ]
            for i in range(len(corrected))
        ],
        "summary": {
            "count": count,
            "pass_count": pass_count,
            "max_abs_adjustment": max_abs_adjustment,
            "quality": "pass" if pass_count == count else "fail",
        },
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"batch: could not be serialized to JSON: {exc}") from exc
