"""Built-in decision engines available to the Apex runtime.

This module only defines the built-in engine catalog. It does not execute
engines or make trading decisions.
"""

from prediction import (
    BreakoutEngine,
    EarlyMovementEngine,
    PredictionEngine,
    ReversalEngine,
    SixtyMinuteEngine,
    MovementPathEngine,
    EnsembleEngine,
    ProbabilityEngine,
    RankingEngine,
)

from research import (
    CorrelationEngine,
    EventImpactEngine,
    FundamentalEngine,
    GlobalImpactEngine,
    MomentumEngine,
    NewsIntelligence,
    PatternEngine,
    PriceActionEngine,
    SentimentEngine,
    TechnicalEngine,
    VolumeEngine,
)


BUILTIN_ENGINE_CLASSES = (
    # ---------------------------------------------------------
    # RESEARCH EVIDENCE
    # ---------------------------------------------------------

    TechnicalEngine,
    MomentumEngine,
    VolumeEngine,
    PriceActionEngine,
    PatternEngine,
    NewsIntelligence,
    SentimentEngine,
    EventImpactEngine,
    FundamentalEngine,
    GlobalImpactEngine,
    CorrelationEngine,

    # ---------------------------------------------------------
    # PRIMARY PREDICTION
    # ---------------------------------------------------------

    PredictionEngine,
    BreakoutEngine,
    EarlyMovementEngine,
    ReversalEngine,
    SixtyMinuteEngine,

    # ---------------------------------------------------------
    # DERIVED / META ANALYSIS
    #
    # These engines consume upstream evidence and must NOT be
    # treated as independent voting engines by ApexMasterBrain.
    # ---------------------------------------------------------

    MovementPathEngine,
    EnsembleEngine,
    ProbabilityEngine,
    RankingEngine,
)


__all__ = [
    "BUILTIN_ENGINE_CLASSES",
]
