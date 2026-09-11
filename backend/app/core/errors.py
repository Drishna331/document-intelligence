class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details
        self.result = None

    def payload(self, request_id=None):
        error = {'code': self.code, 'message': self.message}
        if request_id:
            error['request_id'] = request_id
        if self.details is not None:
            error['details'] = self.details
        payload = {'error': error, 'processing_status': 'FAILED'}
        if self.result is not None:
            payload['result'] = self.result.model_dump(mode='json')
        return payload
