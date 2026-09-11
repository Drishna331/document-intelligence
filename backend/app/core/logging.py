import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger('document_intelligence')


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def event(stage, request_id, **data):
    # Callers pass stage identifiers, counts and error codes, never exception text,
    # request bodies, document contents, provider payloads or secret configuration.
    logger.info(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                            'stage': stage, 'request_id': request_id, **data}))
