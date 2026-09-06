"""Error taxonomy the worker uses to decide retry vs. fail-fast (section 9,
"Worker Loop") and the client-visible error codes from section 9.3/20.
"""


class RetryableError(Exception):
    """Transient failure (network blip, rate limit). Leave the SQS message
    for redelivery; do not mark the document FAILED.
    """


class PermanentError(Exception):
    """Non-retryable failure. Carries a stable `error_code` the frontend can
    show without reading worker logs (blueprint section 3, "See processing
    progress").
    """

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class ScannedPdfError(PermanentError):
    def __init__(self, message: str = "PDF has no extractable text; likely a scanned/image-only document"):
        super().__init__("SCANNED_PDF_REQUIRES_OCR", message)


class ParseError(PermanentError):
    def __init__(self, message: str):
        super().__init__("PARSE_ERROR", message)


class UnsupportedMimeTypeError(PermanentError):
    def __init__(self, message: str):
        super().__init__("UNSUPPORTED_MIME_TYPE", message)
