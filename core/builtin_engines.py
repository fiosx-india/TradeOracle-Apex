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
    # Research evidence stage.
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

    # Primary prediction stage.
    PredictionEngine,
    BreakoutEngine,
    EarlyMovementEngine,
    ReversalEngine,
    SixtyMinuteEngine,
)


__all__ = ["BUILTIN_ENGINE_CLASSES"]
