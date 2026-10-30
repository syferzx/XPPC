"""Offline protocol construction; no APK, captured profile or DNS service needed."""
from portal_client import portal_key
from ranger_native_runtime import Runtime
from slb_protocol import SlbProtocol

def codec():
    runtime=Runtime();ctx=runtime.alloc(64);raw=runtime.alloc(24)
    runtime.assign(raw,portal_key());runtime.call(0x30121c,ctx,raw)
    return SlbProtocol(runtime.string(ctx+8))

