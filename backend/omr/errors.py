class UnsupportedScore(ValueError):
    """A supported file was read, but this score cannot safely enter playback."""


class RecognitionUncertain(UnsupportedScore):
    """A second preprocessing scale may help; no accuracy promise is implied."""


class RecognitionTimeout(RuntimeError):
    pass


class RecognitionAttemptsFailed(RecognitionUncertain):
    """Keep both diagnostics when changing image scale does not resolve uncertainty."""

    def __init__(self, initial, retry=None):
        self.initial = initial
        self.retry = retry
        # Context wrappers reconstruct exception types with a single message.
        if retry is None:
            super().__init__(str(initial))
            return
        super().__init__(
            f'两次识别均未通过检查。首次：{initial} 重试：{retry} '
            '以上是识别结果的异常，不代表原谱有误；请尝试清晰原图或较短片段。')
