__all__ = [
    "DeterministicGeneratorProvider",
    "DeterministicJudgeProvider",
    "JudgeFeedback",
    "JudgeProvider",
    "ResumeGeneratorProvider",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        from . import providers

        return getattr(providers, name)
    raise AttributeError(name)
