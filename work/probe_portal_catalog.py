"""Read movie and series catalog pages with the recovered legitimate portal session."""
import json
from portal_client import ROOT
from probe_portal_session import build_client

def authenticated_client():
    client,_,directory=build_client()
    session=json.loads((directory/'active-data.private.json').read_text(encoding='utf8'))
    portal=session['portalCodeList'][0]['portalCode']
    client.metadata['portalCode']=portal
    client.headers.update(userId=session['userId'],userIdentity=session.get('userIdentity',''))
    return client,{'userId':session['userId'],'userToken':session['userToken'],'portalCode':portal},directory

