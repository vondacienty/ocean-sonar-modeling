"""Vessel attitude correction of single-beam soundings.

Each observation ``(x, y, d, roll, pitch, heave)`` gives the acoustic
offset ``(x, y, d)`` in metres (``d`` positive down), the vessel
attitude ``roll``/``pitch`` in degrees and the ``heave`` in metres
(positive up). The offset is rotated about the x axis by ``roll`` and
then about the y axis by ``pitch``, and the heave is subtracted from
the resulting depth::

    X = cp * x + sp * (sr * y + cr * d)
    Y = cr * y - sr * d
    D = -sp * x + cp * (sr * y + cr * d) - heave

where ``r``/``p`` are ``roll``/``pitch`` in radians and ``cr``/``sr``,
``cp``/``sp`` their cosines/sines.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["correct"]

_FIELDS = ("x", "y", "d", "roll", "pitch", "heave")


def correct(observations):
    """Correct sounding offsets for vessel roll, pitch and heave.

    ``observations`` is a non-empty list/tuple whose items are
    six-element lists/tuples ``(x, y, d, roll, pitch, heave)``. Every
    value must be a finite non-bool int/float and ``d`` must be
    ``>= 0``. Lengths are in metres, angles in degrees and ``heave``
    is positive up.

    Validation order (first error wins): the outer container, its
    non-emptiness, then each item in order (item container, length,
    then ``x``, ``y``, ``d``, ``roll``, ``pitch``, ``heave`` — type,
    finiteness and, for ``d``, non-negativity per value). Container
    and value type errors raise ``TypeError``; emptiness, a non
    six-element item, a non-finite value and ``d < 0`` raise
    ``ValueError``. Item errors are prefixed with
    ``"observation[i]: "``.

    Returns a tuple of ``(X, Y, D)`` float triples in observation
    order, each component rounded to 6 decimals (negative zero
    normalized to ``0.0``). The input is not modified.
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
            raise TypeError(prefix + "item must be a list or tuple")
        if len(obs) != 6:
            raise ValueError(prefix + "item must have 6 elements")
        for name, value in zip(_FIELDS, obs):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
            if name == "d" and not value >= 0:
                raise ValueError(prefix + "d must be >= 0")

        x, y, d, roll, pitch, heave = obs
        r = math.radians(roll)
        p = math.radians(pitch)
        cr, sr = math.cos(r), math.sin(r)
        cp, sp = math.cos(p), math.sin(p)
        components = (
            cp * x + sp * (sr * y + cr * d),
            cr * y - sr * d,
            -sp * x + cp * (sr * y + cr * d) - heave,
        )
        triple = []
        for component in components:
            v = round(component, 6)
            triple.append(0.0 if v == 0 else float(v))
        results.append(tuple(triple))
    return tuple(results)
