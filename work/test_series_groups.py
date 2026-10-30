import sys,tempfile,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'outputs/windows-hls-player'))
from portal import PortalService,public_item,series_identity
from progress import Progress

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        self.service=PortalService(self.temp.name);self.calls=[]
        self.service.request=lambda *args:{'assetData':{}}
        self.assets=[{'contentId':'two','name':'Motive T2'},{'contentId':'one','name':'Motive Temp.1'},{'contentId':'three','name':'Motive T3'},{'contentId':'other','name':'Motive - Español T1'}]
        self.items=[public_item(a,'series') for a in self.assets]
        self.service.assets[self.items[0]['id']]=('series',self.assets[0])
        def search(query,page=1):
            self.calls.append((query,page));matches=[self.items[0],self.items[3]] if page==1 else self.items[1:3]
            for item in matches:self.service.assets[item['id']]=('series',next(a for a in self.assets if a['contentId'] in {'two','one','three','other'} and public_item(a,'series')['id']==item['id']))
            return {'items':matches,'has_more':page==1}
        self.service.search=search
    def test_all_matching_seasons_across_search_pages(self):
        result=self.service.seasons(self.items[0]['id'])
        self.assertEqual([i['season_number'] for i in result['items']],[1,2,3])
        self.assertEqual(result['title'],'Motive');self.assertTrue(result['complete'])
        self.assertEqual(self.calls,[('Motive',1),('Motive',2)])
    def test_last_watched_season_uses_existing_progress(self):
        progress=Progress(self.temp.name);progress.save({'id':self.items[2]['id'],'episode':'4','position':121,'duration':1800})
        result=self.service.seasons(self.items[0]['id']);self.assertEqual(result['resume_id'],self.items[2]['id'])
        self.assertNotIn('token',json.dumps(result));self.assertNotIn('stream_url',json.dumps(result))
    def test_suffixes_and_distinct_variants(self):
        for name in ('Motive T2','Motive Temp.2','Motive Temporada 2','Motive Season 2'):
            self.assertEqual(series_identity(name),('motive','Motive',2))
        self.assertNotEqual(series_identity('Motive Español T1')[0],series_identity('Motive T1')[0])
        self.assertEqual(series_identity('The 100')[2],None)
    def test_explicit_provider_links_take_priority(self):
        self.service.request=lambda *args:{'assetData':{'sameSeasonSeriesList':[{'contentId':'one','seasonNumber':1},{'contentId':'two','seasonNumber':2}]}}
        self.service.search=lambda *args:self.fail('Should use provider season links')
        result=self.service.seasons(self.items[0]['id'])
        self.assertEqual([item['season_number'] for item in result['items']],[1,2])
    def test_duplicate_season_keeps_progress_entry(self):
        self.service.request=lambda *args:{'assetData':{'sameSeasonSeriesList':[{'contentId':'two','seasonNumber':2},{'contentId':'alternate','seasonNumber':2}]}}
        identifier=public_item({'contentId':'alternate'},'series')['id']
        Progress(self.temp.name).save({'id':identifier,'episode':'2','position':80,'duration':1800})
        result=self.service.seasons(self.items[0]['id'])
        self.assertEqual(len(result['items']),1);self.assertEqual(result['resume_id'],identifier)

    def test_same_named_versions_never_share_links_cache_or_progress(self):
        def asset(code,country,season):return {'contentId':code,'name':'The Office T'+str(season),'originalCountry':country}
        us1,us2,uk1,uk2=[asset(*x) for x in [('us1','United States',1),('us2','United States',2),('uk1','United Kingdom',1),('uk2','United Kingdom',2)]]
        rows=[us1,us2,uk1,uk2];ids={a['contentId']:public_item(a,'series')['id'] for a in rows}
        self.service.assets={ids[a['contentId']]:('series',a) for a in rows}
        def request(endpoint,params):
            codes=('us1','us2') if params['contentId'].startswith('us') else ('uk1','uk2')
            return {'assetData':{'sameSeasonSeriesList':[{'contentId':code,'seasonNumber':i+1} for i,code in enumerate(codes)]}}
        self.service.request=request;self.service.search=lambda *args:self.fail('Do not mix title matches with explicit season links')
        Progress(self.temp.name).save({'id':ids['uk1'],'episode':'1','position':945,'duration':1800})
        us=self.service.seasons(ids['us2']);uk=self.service.seasons(ids['uk2'])
        self.assertEqual({x['id'] for x in us['items']},{ids['us1'],ids['us2']});self.assertIsNone(us['resume_id'])
        self.assertEqual({x['id'] for x in uk['items']},{ids['uk1'],ids['uk2']});self.assertEqual(uk['resume_id'],ids['uk1'])
        self.assertNotEqual(us['items'][0]['series_group_key'],uk['items'][0]['series_group_key'])
    def test_fallback_search_does_not_mix_countries(self):
        self.assets[0]['originalCountry']='United States';self.assets[1]['originalCountry']='United States';self.assets[2]['originalCountry']='United Kingdom'
        result=self.service.seasons(self.items[0]['id']);self.assertEqual([x['season_number'] for x in result['items']],[1,2])
    def test_year_comes_from_provider_release_time(self):
        self.assertEqual(public_item({'contentId':'x','releaseTime':'2005-03-24'},'series')['year'],2005)
        self.assertIsNone(public_item({'contentId':'x','releaseTime':''},'movies')['year'])

if __name__=='__main__':unittest.main()
