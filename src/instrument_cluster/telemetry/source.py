from .demo import DemoReader
from .mode import TelemetryMode
from .udp_jsonl import UdpJsonlReader


class TelemetrySource:
    def __init__(
        self,
        mode: TelemetryMode | str | None = None,
        host: str = "127.0.0.1",
        port: int = 5600,
    ):
        if mode is None:
            mode = TelemetryMode.DEMO
        elif isinstance(mode, str):
            mode = TelemetryMode(mode)
        self._mode = mode
        self.reader = (
            UdpJsonlReader(host=host, port=port)
            if mode is TelemetryMode.UDP
            else DemoReader()
        )

    def start(self) -> None:
        self.reader.start()

    def latest(self):
        return self.reader.latest()

    def stop(self) -> None:
        if hasattr(self.reader, "stop"):
            self.reader.stop()
