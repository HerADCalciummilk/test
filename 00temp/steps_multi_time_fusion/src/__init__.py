"""Public STEPS plugin classes."""

__all__ = ["StepsNoisePlugin", "ClimatologicalSkillPlugin", "StepsBlendingPlugin"]


def __getattr__(name):
    if name == "StepsNoisePlugin":
        from steps_multi_time_fusion.src.noise_plugin import StepsNoisePlugin

        return StepsNoisePlugin
    if name == "ClimatologicalSkillPlugin":
        from steps_multi_time_fusion.src.climatological_skill_plugin import ClimatologicalSkillPlugin

        return ClimatologicalSkillPlugin
    if name == "StepsBlendingPlugin":
        from steps_multi_time_fusion.src.steps_blending_plugin import StepsBlendingPlugin

        return StepsBlendingPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
