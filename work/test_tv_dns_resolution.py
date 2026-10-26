import sys,socket,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'work'),str(ROOT/'outputs/windows-hls-player'),str(ROOT/'outputs/ranger-windows')]
from tv import TvService
class DnsTests(unittest.TestCase):
 def service(self):
  s=TvService.__new__(TvService);s.slb_host='tv.example.invalid';s.slb_ip='192.0.2.1';return s
 def answer(self,ip):return (socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))
 def test_uses_current_answers_and_deduplicates(self):
  s=self.service()
  with patch('tv.socket.getaddrinfo',return_value=[self.answer('1.1.1.1'),self.answer('8.8.8.8'),self.answer('1.1.1.1')]) as dns:
   self.assertEqual(s.resolve_slb(s.slb_host),['1.1.1.1','8.8.8.8']);dns.assert_called_once_with(s.slb_host,443,family=socket.AF_INET,type=socket.SOCK_STREAM)
 def test_unknown_host_never_resolves(self):
  with patch('tv.socket.getaddrinfo') as dns:
   with self.assertRaises(ValueError):self.service().resolve_slb('other.invalid')
   dns.assert_not_called()
 def test_dns_failure_never_falls_back_to_old_pin(self):
  with patch('tv.socket.getaddrinfo',side_effect=socket.gaierror()):
   with self.assertRaises(ConnectionError):self.service().resolve_slb('tv.example.invalid')
 def test_private_empty_and_excessive_answers_rejected(self):
  for rows in ([],[self.answer('127.0.0.1')],[self.answer('192.168.1.1')],[self.answer('169.254.1.1')],[self.answer('1.1.1.'+str(i)) for i in range(1,10)]):
   with self.subTest(rows=rows),patch('tv.socket.getaddrinfo',return_value=rows):
    with self.assertRaises(ValueError):self.service().resolve_slb('tv.example.invalid')
if __name__=='__main__':unittest.main()
