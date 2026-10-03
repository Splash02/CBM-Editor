from functools import lru_cache
import ssl
import urllib.request

import certifi


@lru_cache(maxsize=1)
def get_https_context():
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def open_url(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout, context=get_https_context())
