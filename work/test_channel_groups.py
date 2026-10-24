import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/windows-hls-player'))
from channel_groups import channel_groups

class ChannelGroupsTests(unittest.TestCase):
    def test_categories_and_premium_overlap(self):
        self.assertEqual(channel_groups({'name':'TNT SPORTS PREMIUM HD'}),['Deportes','Premium'])
        self.assertEqual(channel_groups({'name':'HBO FAMILY HD'}),['Cine y series','Premium'])
        self.assertEqual(channel_groups({'name':'Discovery Kids HD'}),['Infantiles'])
        self.assertEqual(channel_groups({'name':'CNN HD'}),['Noticias'])
    def test_adult_swim_is_not_adult_content(self):
        self.assertEqual(channel_groups({'name':'Adult Swim'}),['Cine y series'])
    def test_adult_flags_do_not_require_changing_authorization(self):
        channel={'name':'Canal 18+ HD','restricted':'1','isPremium':'0','liveAddressList':[]}
        before=dict(channel)
        self.assertEqual(channel_groups(channel),['Adultos +18'])
        self.assertEqual(channel,before)
        self.assertEqual(channel_groups({'name':'Canal','adult':'0'}),['General y variedades'])
    def test_explicit_category_is_preserved(self):
        self.assertEqual(channel_groups({'name':'Canal Premium','groupName':'Cultura'}),['Cultura','Premium'])
    def test_tags_are_not_guessed_as_access_or_category(self):
        self.assertEqual(channel_groups({'name':'Canal desconocido','tags':'x','restricted':'0'}),['General y variedades'])

if __name__=='__main__':unittest.main()
