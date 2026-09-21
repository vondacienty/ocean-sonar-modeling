"""Vessel attitude correction of single-beam soundings.

Each observation ``(x, y, d, roll, pitch, heave)`` gives the beam
offsets ``x``/``y`` and the measured depth ``d`` (metres, ``d >= 0``)
together with the vessel ``roll``/``pitch`` (degrees) and ``heave``
(metres, positive up) at sounding time. The corrected position applies
the roll rotation about the x axis followed by the pitch rotation about
the y axis, then subtracts heave from the resulting depth.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["correct"]

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
