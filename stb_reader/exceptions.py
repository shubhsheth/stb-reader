class STBError(Exception):
    pass


class AuthError(STBError):
    pass


class StreamError(STBError):
    pass


class NotFoundError(STBError):
    pass
