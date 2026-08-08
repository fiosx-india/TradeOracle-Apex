"""News/event source adapter. Raw news stays in backend."""
class NewsData:
    name = "NewsData"
    capabilities = ["NEWS_DATA"]
    def fetch(self, **kwargs):
        return []
