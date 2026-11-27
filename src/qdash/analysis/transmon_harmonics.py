"""Fit a two-harmonic transmon Hamiltonian to the GE, EF, and FH frequencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.linalg import eigh
from scipy.optimize import least_squares

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Compare candidate spectra at 1 kHz, finer than the task's measurement residual limit.
_SPECTRUM_TOLERANCE_GHZ = 1e-6


@dataclass(frozen=True)
class TransmonHarmonicsFit:
    """Fitted energies and largest absolute transition residual, all in GHz."""

    ec: float
    ej1: float
    ej2: float
    max_abs_residual: float
    success: bool
    message: str
    active_bounds: tuple[str, ...]


def fit_transmon_harmonics(
    ge_frequency: float, ef_frequency: float, fh_frequency: float
) -> TransmonHarmonicsFit:
    """Fit EC, EJ1, and EJ2 in GHz with zero offset charge and charge states -40 to 40.

    Raise ValueError when distinct fitted energies reproduce the same spectrum.
    """
    measured = np.array([ge_frequency, ef_frequency, fh_frequency], dtype=np.float64)
    if not np.all(np.isfinite(measured)) or np.any(measured <= 0):
        raise ValueError("GE, EF, and FH frequencies must be finite and positive")

    charge = np.arange(-40, 41)
    charge_weights = 4.0 * charge**2
    charging_term = np.diag(charge_weights)
    # eigh reads the lower triangle. Cos(k*phi) couples charges k apart.
    first_harmonic = np.diag(np.full(charge.size - 1, -0.5), k=-1)
    second_harmonic = np.diag(np.full(charge.size - 2, -0.5), k=-2)

    def hamiltonian(energies: NDArray[np.float64]) -> NDArray[np.float64]:
        ec, ej1, ej2 = energies
        matrix: NDArray[np.float64] = (
            charging_term * ec + first_harmonic * ej1 + second_harmonic * ej2
        )
        return matrix

    def residual(energies: NDArray[np.float64]) -> NDArray[np.float64]:
        levels: NDArray[np.float64] = eigh(
            hamiltonian(energies), eigvals_only=True, subset_by_index=(0, 3)
        )
        return np.diff(levels) - measured

    def jacobian(energies: NDArray[np.float64]) -> NDArray[np.float64]:
        _, states = eigh(hamiltonian(energies), subset_by_index=(0, 3))
        # Level derivatives are expectations of the corresponding Hamiltonian terms.
        level_derivatives = np.column_stack(
            (
                (states**2).T @ charge_weights,
                -(states[:-1] * states[1:]).sum(axis=0),
                -(states[:-2] * states[2:]).sum(axis=0),
            )
        )
        return np.diff(level_derivatives, axis=0)

    lower_bounds = (0.001, 0.001, -10.0)
    upper_bounds = (10.0, 1000.0, 10.0)
    anharmonicity = max(ge_frequency - ef_frequency, lower_bounds[0])
    fitted = []
    # The reference seed starts with EJ2=0 and EC near the magnitude of the anharmonicity.
    # Vary EC and use the quadratic and quartic potential terms to seed EJ1 and EJ2.
    for factor in (1.0, 0.75, 1.25):
        ec = anharmonicity * factor
        curvature = (ge_frequency + anharmonicity) ** 2 / (8.0 * ec)
        ej2 = curvature * (1.0 / factor - 1.0) / 12.0
        ej1 = curvature - 4.0 * ej2
        seed = np.clip((ec, ej1, ej2), lower_bounds, upper_bounds)
        fitted.append(
            least_squares(residual, x0=seed, jac=jacobian, bounds=(lower_bounds, upper_bounds))
        )

    fit = min(fitted, key=lambda candidate: (not candidate.success, candidate.cost))
    if not np.all(np.isfinite(fit.x)) or not np.all(np.isfinite(fit.fun)):
        raise ValueError("Transmon harmonic fit returned non-finite energies or residuals")
    if fit.success and any(
        candidate.success
        and np.max(np.abs(candidate.fun - fit.fun)) <= _SPECTRUM_TOLERANCE_GHZ
        and not np.allclose(candidate.x, fit.x, rtol=1e-3, atol=1e-5)
        for candidate in fitted
    ):
        raise ValueError("Distinct transmon harmonic fits reproduce the same transition spectrum")

    ec, ej1, ej2 = (float(energy) for energy in fit.x)
    return TransmonHarmonicsFit(
        ec=ec,
        ej1=ej1,
        ej2=ej2,
        max_abs_residual=float(np.max(np.abs(fit.fun))),
        success=bool(fit.success),
        message=str(fit.message),
        active_bounds=tuple(
            name
            for name, active in zip(("EC", "EJ1", "EJ2"), fit.active_mask, strict=True)
            if active
        ),
    )
