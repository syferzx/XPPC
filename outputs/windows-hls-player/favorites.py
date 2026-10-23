"""Local favorites, independent of the browser port; never store playback grants."""
import hashlib,json,threading,time
from pathlib import Path
from artwork import public_image

class Favorites:
    def __init__(self,root,portal,tv):
        self.file=Path(root)/'work/library/favorites.json';self.portal=portal;self.tv=tv;self.lock=threading.RLock()
    def read(self):
        if not self.file.exists():return []
        if self.file.stat().st_size>2*1024*1024:raise ValueError('Favorites file exceeds limit')
        value=json.loads(self.file.read_text(encoding='utf8'))
        if value.get('version')!=1 or not isinstance(value.get('items'),list) or len(value['items'])>500:raise ValueError('Unsupported favorites data')
        return value['items']
    def public(self,rows):
        items=[]
        for row in rows:
            kind=row.get('kind');code=row.get('content_id');identifier=row.get('id')
            if kind not in ('tv','movies','series') or not isinstance(code,str):continue
            if identifier!=hashlib.sha256((kind+':'+code).encode()).hexdigest()[:20]:continue
            item={'id':identifier,'kind':kind,'name':str(row.get('name') or 'Sin título')[:240],
                'groups':[],'genres':str(row.get('genres') or '')[:300],'description':str(row.get('description') or '')[:3000],
                'poster_url':public_image(row.get('poster_url')),'backdrop_url':public_image(row.get('backdrop_url')),
                'number':str(row.get('number') or '')[:20],'playable':kind=='tv','saved_unix':row.get('saved_unix',0)}
            if kind!='tv':
                # Detail and play can resolve this item after a process restart,
                # without paging through the catalog to repopulate assets.
                asset={'contentId':code,'type':row.get('type','0' if kind=='series' else '1'),'name':item['name'],
                       'description':item['description'],'tags':item['genres'],'posterUrl':item['poster_url'],
                       'posterList':[{'fileType':typ,'fileUrl':url} for typ,url in [('icon',item['poster_url']),('poster',item['backdrop_url'])] if url]}
                with self.portal.lock:self.portal.assets.setdefault(identifier,(kind,asset))
            items.append(item)
        return items
    def list(self):
        with self.lock:return {'items':self.public(self.read()),'storage':'local_profile'}
    def change(self,identifier,action):
        if action not in ('add','remove'):raise ValueError('Invalid favorites action')
        with self.lock:
            rows=self.read()
            if action=='remove':rows=[row for row in rows if row.get('id')!=identifier]
            elif not any(row.get('id')==identifier for row in rows):
                if len(rows)>=500:raise ValueError('Favorites limit reached')
                with self.portal.lock:entry=self.portal.assets.get(identifier)
                if entry:
                    kind,asset=entry
                    from portal import public_item
                    item=public_item(asset,kind);code=str(asset['contentId']);typ=asset.get('type','0' if kind=='series' else '1')
                else:
                    with self.tv.lock:channel=self.tv.channels.get(identifier)
                    if not channel:raise ValueError('Unknown catalog item')
                    from artwork import artwork
                    kind='tv';code=str(channel['channelCode']);typ=''
                    item={'name':channel.get('name','Canal'),'number':channel.get('channelNumber',''),**artwork(channel)}
                # Explicit metadata allowlist: no source URLs, tokens or licenses.
                row={key:item.get(key) for key in ('name','genres','description','poster_url','backdrop_url','number')}
                for key,limit in [('name',240),('genres',300),('description',3000),('number',20)]:row[key]=str(row.get(key) or '')[:limit]
                row.update(id=identifier,kind=kind,content_id=code,type=typ,saved_unix=time.time());rows.insert(0,row)
            self.file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.file.with_suffix('.tmp');temporary.write_text(json.dumps({'version':1,'items':rows},ensure_ascii=False),encoding='utf8');temporary.replace(self.file)
            return {'items':self.public(rows),'storage':'local_profile'}
