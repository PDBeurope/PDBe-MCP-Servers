from html.parser import HTMLParser


class HTMLStripper:
    """
    A static class that strips HTML tags from a string.
    """

    @staticmethod
    def strip_tags(html: str) -> str:
        class _HTMLParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.fed: list[str] = []

            def handle_data(self, d: str) -> None:
                self.fed.append(d)

            def get_data(self) -> str:
                return " ".join(self.fed)

        parser = _HTMLParser()
        parser.feed(html)
        return parser.get_data()
