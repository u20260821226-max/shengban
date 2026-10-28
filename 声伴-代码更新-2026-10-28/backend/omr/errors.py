class UnsupportedScore(ValueError):
    """A supported file was read, but this score cannot safely enter playback."""


class RecognitionUncertain(UnsupportedScore):
    """A second preprocessing scale may help; no accuracy promise is implied."""


class RecognitionTimeout(RuntimeError):
    pass
