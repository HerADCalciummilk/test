class PostProcessingPlugin:
    def process(self, *args, **kwargs):
        return None


class BrokenDemoPlugin(PostProcessingPlugin):
    def __init__(self):
        self.name = "broken"

    def process(self, *args, **kwargs):
        pass
