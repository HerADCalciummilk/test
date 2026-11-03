from nimm_g_interp.src.fast_refine_interp_plugin import FastRefineInterpPlugin


def test_plugin_can_be_constructed():
    plugin = FastRefineInterpPlugin(work_dir="D:/tmp/EC_12P5KM", model_region="EC_12P5KM")
    assert plugin.model_region == "EC_12P5KM"
    assert plugin.operation == "i"
