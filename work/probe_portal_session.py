"""Portal client for this installation's own persistent identity.

Does not activate a new identity, log in, clear Android state, or print secrets.
"""
from pathlib import Path
import json
import re
import urllib.error
import urllib.parse
from portal_client import ROOT, PortalClient, PUBLIC_DNS_RESOLVER

def build_client():
    directory = ROOT / 'work/portal-native'
    independent = directory / 'client-profile.private.json'
    if independent.exists():
        profile = json.loads(independent.read_text(encoding='utf8'))
        if profile.get('schema') != 1:
            raise ValueError('Unsupported installation profile')
        client = PortalClient(profile['hosts'], profile['headers'],
                              profile['metadata'], profile.get('resolved') if profile.get('dns_resolver')==PUBLIC_DNS_RESOLVER else {})
        client.dns_resolver=dict(PUBLIC_DNS_RESOLVER)
        return client, profile.get('device_params', {}), directory
    raise ValueError('Installation profile missing; initialize this installation normally')


