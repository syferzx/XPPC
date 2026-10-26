"""Serialized portal access, persistent heartbeat and paginated VOD metadata."""
import hashlib
import json
import threading
import time
import collections
import re
import unicodedata
from pathlib import Path
from probe_portal_catalog import authenticated_client
from artwork import artwork


class PortalSessionConflict(RuntimeError):
    """The provider reports that this session was replaced on another device."""

class PortalSessionExpired(RuntimeError):
    """An existing installation needs a valid ordinary sign-in session."""

def same_user_id(value,expected):
    """Provider DTOs use both JSON integers and decimal identifier strings."""
    return (type(value) in (str,int) and type(expected) in (str,int)
            and bool(str(value)) and bool(str(expected)) and str(value)==str(expected))


def recover_existing_session(root):
    """Sign in the same registered installation; never create or rotate identities."""
    from probe_portal_session import build_client
    directory=Path(root)/'work/portal-native'
    old=json.loads((directory/'active-data.private.json').read_text(encoding='utf8'))
    profile=json.loads((directory/'client-profile.private.json').read_text(encoding='utf8'))
    identity=json.loads((directory/'installation.private.json').read_text(encoding='utf8'))
    params=profile.get('device_params',{})
    if not identity.get('installation_id') or params.get('serialNumber')!=identity['installation_id']:
        raise PortalSessionExpired('Existing installation identity unavailable')
    client,_,actual_directory=build_client()
    if Path(actual_directory).resolve()!=directory.resolve():raise PortalSessionExpired('Profile location differs')
    _,_,token=client.request('/api/portalCore/v3/snToken',params)
    data=token.get('data')
    if str(token.get('returnCode'))!='0' or not isinstance(data,dict) or not data.get('snToken'):
        raise PortalSessionExpired('Existing installation not accepted')
    # For an already registered device the provider returns isNew="1" together
    # with its existing userId and SN. Require both to match before continuing;
    # the flag alone must neither reject that login nor authorize a new account.
    if data.get('isNew') in (True,1,'1','true') and (
        not old.get('userId') or not same_user_id(data.get('userId'),old['userId'])
        or not profile.get('metadata',{}).get('sn')
        or data.get('sn')!=profile['metadata']['sn']):
        raise PortalSessionExpired('Existing account and installation were not confirmed')
    sn=data.get('sn')
    if sn and sn!=profile.get('metadata',{}).get('sn'):raise PortalSessionExpired('Installation changed')
    _,_,response=client.request('/api/portalCore/v8/active',{'snToken':data['snToken'],'authVersion':'','authCode':'',
        'macAddr':'02:00:00:00:00:00','reserve1':'','openNum':1,'channel':'default','matadata':'','signdata':''})
    session=response.get('data')
    if (str(response.get('returnCode'))!='0' or not isinstance(session,dict) or not session.get('userToken')
        or not same_user_id(session.get('userId'),old.get('userId')) or not session.get('portalCodeList')):
        raise PortalSessionExpired('Same-account sign-in not accepted')
    temporary=directory/'active-data.private.tmp'
    temporary.write_text(json.dumps(session,ensure_ascii=False),encoding='utf8')
    temporary.replace(directory/'active-data.private.json')


def series_identity(name):
    name=' '.join(str(name).split())
    match=re.search(r'\s+(?:T|Temp\.?|Temporada|Season)\s*(\d+)\s*$',name,re.I)
    title=name[:match.start()].strip() if match else name
    return unicodedata.normalize('NFC',title).casefold(),title,int(match[1]) if match else None


def series_group_identity(asset):
    title=series_identity(asset.get('name',''))[0]
    country=' '.join(str(asset.get('originalCountry') or '').split()).casefold()
    return title,country


def series_group_token(asset):
    return hashlib.sha256(('series-group:'+repr(series_group_identity(asset))).encode()).hexdigest()[:20]


def public_year(value):
    match=re.match(r'^(\d{4})(?:[-/]|$)',str(value or ''))
    return int(match[1]) if match and 1880<=int(match[1])<=2100 else None


def public_item(asset, kind):
    code = str(asset['contentId'])
    return {'id': hashlib.sha256((kind + ':' + code).encode()).hexdigest()[:20],
            'name': asset.get('name', 'Sin título'), 'kind': kind, 'groups': [],
            'description': asset.get('description', ''), 'genres': asset.get('tags', ''),
            'cast': asset.get('actorDisplay', ''), 'score': asset.get('score'),
            'year':public_year(asset.get('releaseTime')),'series_country':str(asset.get('originalCountry') or '')[:120] if kind=='series' else '',
            'series_group_key':series_group_token(asset) if kind=='series' else None,
            'episodes': asset.get('volumnCount', 0), 'duration': asset.get('duration', ''),
            'programType': asset.get('programType', ''), 'playable': False,**artwork(asset)}


class PortalService:
    columns = {'movies': 76263, 'series': 76235, 'anime': 76209}

    def __init__(self, root, client_factory=authenticated_client, session_recovery=recover_existing_session):
        self.root = Path(root)
        self.directory = self.root / 'work/portal-native'
        self.factory = client_factory
        self.session_recovery=session_recovery
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.client = None
        self.auth = None
        self.pages = {}
        self.home_pages = {}
        self.series_groups = {}
        self.assets = {}
        self.searches = collections.OrderedDict()
        self.state = {'connected': False, 'last_heartbeat_unix': None,
                      'last_catalog_unix': None, 'last_error': None,
                      'video_renewal_verified': False}

    def status(self):
        with self.lock:
            return dict(self.state)

    def connect(self):
        if self.client is None:
            self.client, self.auth, _ = self.factory()

    def request(self, endpoint, params):
        with self.lock:
            return self._request(endpoint,params)

    def _request(self, endpoint, params):
        self.connect()
        _, _, response = self.client.request(endpoint, {**self.auth, **params})
        if str(response.get('returnCode')) in ('aaa100027','aaa100028'):
            self.state.update(connected=False,last_error='session_expired')
            ledger=self.directory/'session-recovery.private.json'
            try:previous=json.loads(ledger.read_text(encoding='utf8')).get('attempt_unix',0)
            except (OSError,ValueError,TypeError):previous=0
            if time.time()-previous<60:raise PortalSessionExpired('Sign-in recovery already attempted')
            self.directory.mkdir(parents=True,exist_ok=True)
            ledger.write_text(json.dumps({'attempt_unix':time.time()}),encoding='utf8')
            self.session_recovery(self.root)
            self.client=None;self.connect()
            _,_,response=self.client.request(endpoint,{**self.auth,**params})
            if str(response.get('returnCode')) in ('aaa100027','aaa100028'):
                raise PortalSessionExpired('Sign-in session still rejected')
            self.state.update(last_session_recovery_unix=time.time())
        if str(response.get('returnCode')) == 'aaa100083':
            self.state.update(connected=False, last_error='session_conflict')
            raise PortalSessionConflict('Session replaced on another device')
        if str(response.get('returnCode')) != '0':
            raise RuntimeError('Portal rejected request')
        data = response.get('data')
        if not isinstance(data, dict):
            raise ValueError('Unexpected portal data')
        return data

    def heartbeat(self):
        with self.lock:
            data = self.request('/api/portalCore/v5/heartbeat', {})
            token = data.get('userToken')
            if not isinstance(token, str) or not token:
                raise ValueError('Heartbeat missing session token')
            file = self.directory / 'active-data.private.json'
            session = json.loads(file.read_text(encoding='utf8'))
            session.update({k: data[k] for k in ['userToken', 'jwtToken', 'availableTime'] if k in data})
            temporary = file.with_suffix('.tmp')
            temporary.write_text(json.dumps(session, ensure_ascii=False), encoding='utf8')
            temporary.replace(file)
            self.auth['userToken'] = token
            self.state.update(connected=True, last_heartbeat_unix=time.time(), last_error=None)
            # The portal heartbeat maintains userToken. It does not renew Content-Auth.
            return data

    def page(self, kind, page=1, refresh=False, category=None):
        if kind not in self.columns or type(page) is not int or not 1 <= page <= 2000:
            raise ValueError('Invalid catalog page')
        column=self.columns[kind]
        if category:
            allowed={str(row['id']) for row in self.categories(kind)['items']}
            if str(category) not in allowed:raise ValueError('Unknown category')
            column=int(category)
        key = (kind, page, column)
        with self.lock:
            cached = self.pages.get(key)
            if cached and not refresh and time.time() - cached['fetched_unix'] < 300:
                return cached
            file=self.root/'work'/('catalog-first-'+kind+'-'+str(column)+'.json')
            data=None;fetched=time.time()
            if page==1 and not refresh:
                try:
                    if file.stat().st_size<2*1024*1024:
                        saved=json.loads(file.read_text(encoding='utf8'))
                        if (0<=time.time()-saved['fetched_unix']<300
                            and isinstance(saved['data']['assetList'],list)
                            and len(saved['data']['assetList'])<=40
                            and all(isinstance(a,dict) and a.get('contentId') for a in saved['data']['assetList'])
                            and type(saved['data']['assetListTotalSize']) is int):
                            data=saved['data'];fetched=saved['fetched_unix']
                except (OSError,ValueError,KeyError,TypeError):pass
            if data is None:
                data = self.request('/api/portalCore/v3/getShelveData', {
                    'columnId': column, 'columnType': '2',
                    'pageNum': page, 'pageSize': 40, 'encryptVersion': 0})
                fetched=time.time()
            assets = data.get('assetList')
            total = data.get('assetListTotalSize')
            if not isinstance(assets, list) or not isinstance(total, int) or len(assets) > 40:
                raise ValueError('Invalid catalog response')
            if page==1:
                try:
                    file.parent.mkdir(parents=True,exist_ok=True)
                    temporary=file.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'data':{'assetList':assets,'assetListTotalSize':total},'fetched_unix':fetched},ensure_ascii=False),encoding='utf8')
                    temporary.replace(file)
                except OSError:pass
            items = []
            for asset in assets:
                item_kind = ('series' if asset.get('programType') == 'teleplay' or str(asset.get('type')) == '0' else 'movies') if kind == 'anime' else kind
                item = public_item(asset, item_kind)
                self.assets[item['id']] = (item_kind, asset)
                items.append(item)
            result = {'items': items, 'kind': kind, 'page': page, 'page_size': 40,
                      'total': total, 'has_more': page * 40 < total,
                      'fetched_unix': fetched}
            self.pages[key] = result
            self.state.update(last_catalog_unix=time.time(), last_error=None)
            return result

    def original_rows(self,kind):
        key=('rows',kind)
        cached=self.home_pages.get(key)
        if cached and time.time()-cached['fetched_unix']<300:return cached['rows']
        file=self.root/'work'/('home-rows-'+kind+'.json')
        try:
            if file.stat().st_size<8*1024*1024:
                saved=json.loads(file.read_text(encoding='utf8'))
                if isinstance(saved.get('rows'),list) and 0<=time.time()-saved['fetched_unix']<300:
                    self.home_pages[key]=saved
                    return saved['rows']
        except (OSError,ValueError,KeyError,TypeError):pass
        data=self.request('/api/portalCore/getHome',{'homePageCode':'masnew_'+kind,'version':''})
        rows=data.get('recommendList')
        if not isinstance(rows,list):raise ValueError('Invalid home rows')
        self.home_pages[key]={'rows':rows,'fetched_unix':time.time()}
        try:
            file.parent.mkdir(parents=True,exist_ok=True)
            temporary=file.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.home_pages[key],ensure_ascii=False),encoding='utf8')
            temporary.replace(file)
        except OSError:pass
        return rows

    def categories(self,kind):
        if kind not in self.columns:raise ValueError('Invalid category type')
        with self.lock:
            rows=self.original_rows(kind)
            return {'items':[{'id':str(r['columnId']),'name':r.get('name','Categoría')} for r in rows if str(r.get('columnId','')).isdigit()]}

    def featured(self):
        with self.lock:
            cached=self.home_pages.get('featured')
            if cached and time.time()-cached['fetched_unix']<300:return cached
            rows=self.original_rows('featured')
            data=self.request('/api/portalCore/v3/getRecommends',{'recommendCodeArr':['masnew_featured'+str(i).zfill(2) for i in range(1,7)]})
            def item(asset):
                kind='series' if asset.get('programType')=='teleplay' or str(asset.get('type'))=='0' else 'movies'
                value=public_item(asset,kind)
                from artwork import public_image
                banner=next((public_image(p.get('fileUrl')) for p in asset.get('posterList',[]) if p.get('fileType')=='banner' and public_image(p.get('fileUrl'))),None)
                if banner:value['backdrop_url']=banner;value['poster_url']=value['poster_url'] or banner
                self.assets[value['id']]=(kind,asset)
                return value
            banners=[];seen=set()
            for group in data.get('recommendList',[])[:30]:
                for asset in group.get('contentList',[])[:30]:
                    if not asset.get('contentId'):continue
                    value=item(asset)
                    if value['id'] not in seen:seen.add(value['id']);banners.append(value)
            sections=[{'name':r.get('name','Destacados'),'items':[item(a) for a in r.get('assetList',[])[:20] if a.get('contentId')]} for r in rows[:30] if r.get('assetList')]
            result={'banners':banners,'sections':sections,'fetched_unix':time.time(),'source':'provider_featured'}
            self.home_pages['featured']=result
            return result

    def home(self,kind):
        if kind not in self.columns:raise ValueError('Invalid home category')
        with self.lock:
            cached=self.home_pages.get(kind)
            if cached and time.time()-cached['fetched_unix']<300:return cached
            rows=self.original_rows(kind)
            row=next((r for r in rows if str(r.get('columnId'))==str(self.columns[kind])),None)
            if not isinstance(row,dict) or not isinstance(row.get('assetList'),list):raise ValueError('No original home selection')
            items=[];seen=set()
            for asset in row['assetList'][:100]:
                item=public_item(asset,kind);self.assets[item['id']]=(kind,asset)
                key=item['id']
                if kind=='series':
                    key=series_group_identity(asset)
                if key not in seen:seen.add(key);items.append(item)
            result={'items':items,'kind':kind,'source':'provider_home','source_column':str(row.get('name','')),
                    'selection_label':'Agregados recientemente',
                    'fetched_unix':time.time()}
            self.home_pages[kind]=result
            return result

    def search(self, query, page=1):
        if not isinstance(query,str) or not 2<=len(query.strip())<=120 or type(page) is not int or not 1<=page<=2000:
            raise ValueError('Invalid search')
        query=query.strip();key=(query.casefold(),page)
        with self.lock:
            cached=self.searches.get(key)
            if cached and time.time()-cached['fetched_unix']<300:
                self.searches.move_to_end(key);return cached
            # Verified original searchByName returns both movies and teleplays,
            # including matches on original titles/aliases, across the catalog.
            data=self.request('/api/portalCore/v3/searchByName',{'columnId':str(self.columns['series']),'value':query,'type':'0','pageNum':page,'pageSize':40,'filter':''})
            groups=data.get('searchItemList');total=data.get('totalSize')
            if not isinstance(groups,list) or type(total) is not int or total<0:raise ValueError('Invalid search response')
            assets=[a for group in groups for a in group.get('itemList',[])]
            if len(assets)>40:raise ValueError('Search page exceeds bounds')
            items=[]
            for asset in assets:
                kind='series' if asset.get('programType')=='teleplay' else 'movies'
                item=public_item(asset,kind);self.assets[item['id']]=(kind,asset);items.append(item)
            result={'items':items,'query':query,'page':page,'page_size':40,'total':total,'has_more':page*40<total,'fetched_unix':time.time()}
            self.searches[key]=result;self.searches.move_to_end(key)
            while len(self.searches)>80:self.searches.popitem(last=False)
            return result

    def recommendations(self,item_id):
        with self.lock:
            kind,asset=self.assets[item_id]
            key=('recommendations',item_id);cached=self.home_pages.get(key)
            if cached and time.time()-cached['fetched_unix']<300:return cached
            data=self.request('/api/portalCore/v3/searchByContent',{'contentId':asset['contentId'],'type':asset.get('type','0' if kind=='series' else '1'),'start':0,'end':20,'rows':20})
            assets=data.get('assetList')
            if not isinstance(assets,list):raise ValueError('Invalid recommendations')
            result=[];seen=set()
            for entry in assets[:40]:
                if not entry.get('contentId'):continue
                entry_kind='series' if entry.get('programType')=='teleplay' else 'movies'
                item=public_item(entry,entry_kind)
                self.assets[item['id']]=(entry_kind,entry)
                if item['id']==item_id:continue
                if kind=='series' and entry_kind=='series' and series_group_identity(entry)==series_group_identity(asset):continue
                identity=series_group_identity(entry) if entry_kind=='series' else item['id']
                if identity in seen:continue
                seen.add(identity);result.append(item)
            response={'items':result,'source':'provider','fetched_unix':time.time()}
            self.home_pages[key]=response
            return response

    def seasons(self,item_id):
        with self.lock:
            kind,asset=self.assets[item_id]
            if kind!='series':raise ValueError('Not a series')
            key,title,_=series_identity(asset.get('name',''))
            cache_key=item_id
            cached=self.series_groups.get(cache_key)
            if cached and time.time()-cached['fetched_unix']<300:
                result=dict(cached)
            else:
                complete=True
                detail=self.request('/api/portalCore/v4/getItemData',{'contentId':asset['contentId'],'type':asset.get('type','0'),'sortType':'0','language':'es','macAddr':'02:00:00:00:00:00'}).get('assetData',{})
                for field in ('originalCountry','actorDisplay','releaseTime'):
                    if detail.get(field):asset[field]=detail[field]
                links=detail.get('sameSeasonSeriesList') or []
                linked=[];linked_numbers={}
                for link in links[:100]:
                    code=link.get('contentId');number=link.get('seasonNumber')
                    if not isinstance(code,str) or not code or not str(number).isdigit():continue
                    identifier=hashlib.sha256(('series:'+code).encode()).hexdigest()[:20]
                    if identifier not in self.assets:
                        self.assets[identifier]=('series',{'contentId':code,'name':title+' T'+str(number),'type':'0','programType':'teleplay',
                            'posterList':detail.get('posterList',asset.get('posterList',[])),'description':detail.get('description',''),'tags':detail.get('tags',''),'originalCountry':asset.get('originalCountry',''),'actorDisplay':asset.get('actorDisplay','')})
                    linked.append(identifier)
                    linked_numbers[identifier]=int(number)
                if not linked and 2<=len(title)<=120:
                    # Search the full provider catalog, not only loaded UI pages.
                    for page in range(1,11):
                        data=self.search(title,page)
                        if not data['has_more']:break
                    else:complete=False
                matches=[]
                for identifier,(entry_kind,entry) in list(self.assets.items()):
                    if entry_kind!='series':continue
                    entry_key,_,number=series_identity(entry.get('name',''))
                    matches_group=(identifier in linked or identifier==item_id) if linked else (entry_key==key and series_group_identity(entry)==series_group_identity(asset))
                    if matches_group:
                        item=public_item(entry,'series');item['season_number']=linked_numbers.get(identifier,number);matches.append(item)
                matches.sort(key=lambda item:(item['season_number'] is None,item['season_number'] or 0,item['name'],item['id']))
                result={'title':title,'country':asset.get('originalCountry',''),'items':matches,'complete':complete,'fetched_unix':time.time()}
                self.series_groups[cache_key]=dict(result)
            # Read progress fresh, so reopening uses the last watched season.
            from progress import Progress
            try:marks=Progress(self.root).read()
            except (OSError,ValueError):marks={}
            # Some providers link two catalog entries for the same season.
            # Keep the watched entry (or the one opened), without two T4 options.
            unique={}
            for item in result['items']:
                number=item['season_number'];identity=('season',number) if number is not None else ('item',item['id'])
                previous=unique.get(identity)
                def priority(entry):return (marks.get(entry['id'],{}).get('updated_unix',0),entry['id']==item_id)
                if previous is None or priority(item)>priority(previous):unique[identity]=item
            result['items']=list(unique.values())
            known={item['id'] for item in result['items']}
            watched=[(identifier,mark) for identifier,mark in marks.items() if identifier in known]
            result['resume_id']=max(watched,key=lambda row:row[1].get('updated_unix',0))[0] if watched else None
            return result

    def detail(self, item_id):
        with self.lock:
            kind, asset = self.assets[item_id]
            data = self.request('/api/portalCore/v4/getItemData', {
                'contentId': asset['contentId'], 'type': asset.get('type', '0' if kind == 'series' else '1'),
                'sortType': '0', 'language': 'es', 'macAddr': '02:00:00:00:00:00'})
            detail = data.get('assetData')
            if not isinstance(detail, dict):
                raise ValueError('Invalid title detail')
            programs = detail.get('simpleProgramList', [])
            return {'item': public_item(detail, kind), 'episodes': [
                {'name': p.get('name', ''), 'number': p.get('seriesNumber'),
                 'duration': p.get('duration', '')} for p in programs],
                'playback_ready': False}

    def start(self):
        if self.thread is not None:
            return
        def run():
            while not self.stop.is_set():
                try:
                    self.heartbeat()
                except Exception as error:
                    with self.lock:
                        self.state.update(connected=False, last_error=(
                            'session_conflict' if isinstance(error, PortalSessionConflict)
                            else 'session_expired' if isinstance(error,PortalSessionExpired)
                            else type(error).__name__))
                self.stop.wait(120)
        self.thread = threading.Thread(target=run, name='portal-heartbeat', daemon=True)
        self.thread.start()
