"""Motor local y explicable de recomendaciones para Driver Control.

El MVP ordena reglas financieras por utilidad, no por tiempo de pantalla. No usa
datos de otros conductores ni necesita conexión. Un modelo estadístico futuro puede
reemplazar el ranking, pero debe conservar estas mismas restricciones de seguridad.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class Insight:
    kind: str
    title: str
    message: str
    action: str
    why: str
    score: float


WEIGHTS = {
    "financial_impact": 0.30,
    "actionability": 0.25,
    "personal_relevance": 0.15,
    "timeliness": 0.15,
    "novelty": 0.10,
    "confidence": 0.05,
    "repetition": -0.20,
    "anxiety_risk": -0.25,
    "distraction_risk": -0.30,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _score(signals: Mapping[str, float]) -> float:
    weighted = sum(WEIGHTS[name] * _clamp(signals.get(name, 0.0)) for name in WEIGHTS)
    return round(max(0.0, min(1.0, weighted)) * 100.0, 1)


def _candidate(
    kind: str,
    title: str,
    message: str,
    action: str,
    why: str,
    signals: Mapping[str, float],
) -> Insight:
    return Insight(kind, title, message, action, why, _score(signals))


def rank_financial_insights(
    metrics: Mapping[str, float],
    *,
    daily_goal: float = 0.0,
    confidence: str = "PARTIAL",
    cash_difference: Optional[float] = None,
    seen_kinds: Iterable[str] = (),
    limit: int = 3,
) -> list[Insight]:
    """Devuelve un feed finito de acciones ordenadas por utilidad esperada."""

    income = max(0.0, float(metrics.get("income", metrics.get("revenue", 0.0)) or 0.0))
    profit = float(metrics.get("profit", metrics.get("net", 0.0)) or 0.0)
    fuel_cost = max(0.0, float(metrics.get("fuel_cost", 0.0) or 0.0))
    expenses = max(
        0.0,
        float(metrics.get("expenses", metrics.get("operating_expenses", 0.0)) or 0.0),
    )
    seen = set(seen_kinds)
    candidates: list[Insight] = []

    def repetition(kind: str) -> float:
        return 1.0 if kind in seen else 0.0

    if confidence != "CONFIRMED":
        candidates.append(
            _candidate(
                "complete_data",
                "Tu cierre quedó guardado",
                "Hay datos pendientes, pero no perdiste la jornada.",
                "Completá lo que falta cuando tengas el detalle de Uber.",
                "Los datos completos vuelven más precisa la ganancia.",
                {
                    "financial_impact": 0.55,
                    "actionability": 1.0,
                    "personal_relevance": 1.0,
                    "timeliness": 1.0,
                    "novelty": 0.55,
                    "confidence": 1.0,
                    "repetition": repetition("complete_data"),
                    "anxiety_risk": 0.05,
                },
            )
        )

    if profit < 0:
        candidates.append(
            _candidate(
                "negative_profit",
                "Hoy los costos superaron los ingresos",
                "El resultado quedó debajo de cero; revisá antes de repetir el mismo patrón.",
                "Revisá nafta, gastos y horas trabajadas.",
                "El resultado operativo es negativo.",
                {
                    "financial_impact": 1.0,
                    "actionability": 0.95,
                    "personal_relevance": 1.0,
                    "timeliness": 1.0,
                    "novelty": 0.8,
                    "confidence": 0.9,
                    "repetition": repetition("negative_profit"),
                    "anxiety_risk": 0.30,
                },
            )
        )

    if cash_difference is not None and abs(cash_difference) >= 100.0:
        impact = min(abs(cash_difference) / max(income, 1.0), 1.0)
        candidates.append(
            _candidate(
                "cash_mismatch",
                "Hay una diferencia en la caja",
                "Lo contado no coincide con los cobros y gastos en efectivo registrados.",
                "Buscá un gasto o vuelto que haya quedado sin cargar.",
                "La caja contada y la esperada son distintas.",
                {
                    "financial_impact": max(0.45, impact),
                    "actionability": 1.0,
                    "personal_relevance": 1.0,
                    "timeliness": 1.0,
                    "novelty": 0.7,
                    "confidence": 1.0,
                    "repetition": repetition("cash_mismatch"),
                    "anxiety_risk": 0.15,
                },
            )
        )

    fuel_ratio = fuel_cost / income if income > 0 else 0.0
    if fuel_ratio >= 0.20:
        candidates.append(
            _candidate(
                "fuel_share",
                "La nafta pesó bastante hoy",
                f"Representó aproximadamente {fuel_ratio * 100:.0f}% de tus ingresos.",
                "Compará el próximo cierre y revisá kilómetros sin pasajero.",
                "El combustible superó el 20% de los ingresos.",
                {
                    "financial_impact": min(fuel_ratio * 2.5, 1.0),
                    "actionability": 0.75,
                    "personal_relevance": 1.0,
                    "timeliness": 0.9,
                    "novelty": 0.65,
                    "confidence": 0.85,
                    "repetition": repetition("fuel_share"),
                    "anxiety_risk": 0.05,
                },
            )
        )

    if daily_goal > 0 and income >= daily_goal:
        candidates.append(
            _candidate(
                "goal_met",
                "Meta alcanzada",
                "Cumpliste el objetivo de ingresos de esta jornada.",
                "Cerrá el día y descansá; mañana empieza otro registro.",
                "Los ingresos alcanzaron la meta configurada.",
                {
                    "financial_impact": 0.45,
                    "actionability": 0.55,
                    "personal_relevance": 1.0,
                    "timeliness": 1.0,
                    "novelty": 0.8,
                    "confidence": 1.0,
                    "repetition": repetition("goal_met"),
                },
            )
        )

    if profit >= 0 and expenses + fuel_cost <= income:
        candidates.append(
            _candidate(
                "healthy_close",
                "Ya sabés qué te quedó",
                "La jornada está cerrada y sus costos principales están separados.",
                "Usá este resultado como referencia para tu próxima salida.",
                "El cierre tiene un resultado operativo no negativo.",
                {
                    "financial_impact": 0.40,
                    "actionability": 0.65,
                    "personal_relevance": 0.9,
                    "timeliness": 1.0,
                    "novelty": 0.55,
                    "confidence": 0.9,
                    "repetition": repetition("healthy_close"),
                },
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.kind))
    return candidates[: max(1, int(limit))]
