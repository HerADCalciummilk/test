from demo_plugin import DemoAlgoPlugin


def test_process():
    assert DemoAlgoPlugin().process(1) == 2
