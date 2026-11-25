"""Synthetic evidence classification tests. Never opens a real capture or DB."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_checklist as checklist

class ChecklistTests(unittest.TestCase):
    def setUp(self):self.counts=Counter();self.empty=Counter()
    def event(self,name,body):checklist.observe(name,body,self.counts,self.empty)
    def items(self,**kw):return {i['id']:i for i in checklist.report(self.counts,self.empty,**kw)['items']}
    def test_no_readable_snapshot_is_unknown_not_missing(self):
        self.assertTrue(all(i['state']=='unknown' for i in self.items(phase='capturing').values()))
        self.assertTrue(all(i['state']=='unknown' for i in self.items(phase='complete').values()))
    def test_request_and_error_response_do_not_mark_collected(self):
        self.event('GetWeaponReq',{});self.event('GetWeaponRsp',{'status':2,'weapons':[{}]})
        self.assertEqual(self.items(phase='complete',readable=True)['weapon']['state'],'missing')
    def test_successful_empty_response_is_not_missing(self):
        self.event('GetWeaponRsp',{'status':'StatusCode_OK'})
        self.assertEqual(self.items(phase='capturing',readable=True)['weapon']['state'],'empty')
    def test_main_and_roles_are_confirmed_by_valid_main(self):
        self.event('PlayerMainDataRsp',{'status':1,'player_id':777,'characters':[{'character_id':1}]})
        data=self.items(readable=True)
        self.assertEqual(data['main']['state'],'collected');self.assertEqual(data['characters']['state'],'collected')
    def test_zero_uid_main_is_not_collected(self):
        self.event('PlayerMainDataRsp',{'status':1,'player_id':0})
        self.assertEqual(self.items(phase='complete',readable=True)['main']['state'],'missing')
    def test_inventory_equipment_requires_decoded_instance(self):
        self.event('PackNotice',{'items':[{'main_item':{'weapon':{'instance_id':42,'weapon_id':1},'armor':{'field_2':43}}}]})
        data=self.items(readable=True);self.assertEqual(data['weapon']['state'],'partial')
        self.assertEqual(data['armor']['state'],'waiting')
    def test_equipment_list_upgrades_partial_evidence(self):
        self.event('PackNotice', {'items':[{'main_item':{'weapon':{'instance_id':42}}}]})
        self.event('GetWeaponRsp', {'status':1, 'weapons':[{'instance_id':42}]})
        self.assertEqual(self.items(phase='complete', readable=True)['weapon']['state'], 'collected')

    def test_final_report_warns_about_capture_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'json').mkdir()
            (root / 'summary.json').write_text(json.dumps({
                'incomplete_streams': [
                    {'stream_id': 0, 'direction': 's2c', 'tcp_gap': True, 'trailing_bytes': 0},
                ],
            }), encoding='utf-8')
            (root / 'json/1_s0_s2c_1_GetWeaponRsp.json').write_text(
                json.dumps({'status':1, 'weapons':[{'instance_id':42}]}), encoding='utf-8')
            data = checklist.final_report(root)
            self.assertIn('备份可能不完整', data['warning'])
            weapon = next(item for item in data['items'] if item['id'] == 'weapon')
            self.assertEqual(weapon['state'], 'collected')

    def test_city_scene_does_not_count_as_home(self):
        self.event('SceneDataNotice',{'data':{'scene_id':1001}})
        self.assertEqual(self.items(readable=True)['garden']['state'],'waiting')
        self.event('SceneDataNotice',{'data':{'scene_id':9999}})
        self.assertEqual(self.items(readable=True)['garden']['state'],'collected')
    def test_final_report_ignores_request_counts_and_failed_json(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'json').mkdir()
            (root/'summary.json').write_text(json.dumps({'message_counts':{'GetWeaponRsp':99}}))
            (root/'json/1_s0_s2c_1_GetPetRsp.json').write_text(json.dumps({'status':1,'pets':[]}))
            (root/'json/2_s0_s2c_2_GetMailsRsp.json').write_text(json.dumps({'status':2}))
            result={i['id']:i for i in checklist.final_report(root)['items']}
            self.assertEqual(result['pet']['state'],'empty')
            self.assertEqual(result['weapon']['state'],'missing');self.assertEqual(result['mail']['state'],'missing')
    def test_missing_json_folder_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            result=checklist.final_report(d)
            self.assertTrue(all(i['state']=='unknown' for i in result['items']))


class LiveCaptureTests(unittest.TestCase):
    def test_scans_temporary_copy_before_it_is_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            etl = root / 'capture.etl'
            etl.write_bytes(b'original ETL')
            stop = root / 'live-progress-stop.flag'
            decoder = object()
            results = (Counter({'PlayerLoginRsp': 1}), Counter())
            snapshot_paths = []

            def convert(command, **options):
                self.assertEqual(command[1], 'etl2pcap')
                copied = Path(command[2])
                self.assertNotEqual(copied, etl)
                self.assertEqual(copied.read_bytes(), etl.read_bytes())
                pcap = Path(command[4])
                pcap.write_bytes(bytes(300))
                snapshot_paths.extend((copied, pcap))
                return checklist.subprocess.CompletedProcess(command, 0)

            def scan(current_decoder, pcap, current_stop):
                self.assertIs(current_decoder, decoder)
                self.assertTrue(pcap.is_file())
                self.assertEqual(current_stop, stop)
                return (*results, 1)

            with patch.object(checklist.subprocess, 'run', side_effect=convert) as native, patch.object(
                checklist, 'scan_pcap', side_effect=scan
            ):
                self.assertEqual(checklist.snapshot_pcap(decoder, etl, root, stop), results)
                stop.touch()
                self.assertIsNone(checklist.snapshot_pcap(decoder, etl, root, stop))
                native.assert_called_once()

            self.assertEqual(etl.read_bytes(), b'original ETL')
            self.assertFalse(any(path.exists() for path in snapshot_paths))

    def test_watch_throttles_changed_copies_and_retains_last_readable_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            etl = root / 'capture.etl'
            etl.write_bytes(b'initial')
            clock = 0.0
            reports = {}
            attempts = []

            def advance(seconds):
                nonlocal clock
                clock += seconds
                if clock == 3:
                    etl.write_bytes(b'larger but unreadable')
                elif clock == 30:
                    etl.write_bytes(b'larger and readable again')
                elif clock == 36:
                    (root / 'live-progress-stop.flag').touch()

            def snapshot(decoder, path, live, stop):
                self.assertEqual(path, etl.resolve())
                attempts.append(clock)
                if clock == 12:
                    return None
                count = 1 if clock == 0 else 2
                return Counter({'PlayerLoginRsp': count}), Counter()

            def publish(path, result):
                self.assertEqual(path.name, 'progress.json')
                reports[clock] = result

            with patch.object(checklist, 'load_decoder'), patch.object(
                checklist, 'read_packet_counters', return_value=99
            ), patch.object(checklist, 'snapshot_pcap', side_effect=snapshot), patch.object(
                checklist, 'atomic_json', side_effect=publish
            ), patch.object(checklist.time, 'monotonic', side_effect=lambda: clock), patch.object(
                checklist.time, 'sleep', side_effect=advance
            ):
                checklist.watch(root)

            self.assertEqual(attempts, [0, 12, 30])
            self.assertEqual(reports[12]['counts']['PlayerLoginRsp'], 1)
            self.assertEqual(reports[27]['counts']['PlayerLoginRsp'], 1)
            self.assertEqual(reports[30]['counts']['PlayerLoginRsp'], 2)
            self.assertTrue(reports[12]['readable'])
            self.assertEqual(reports[12]['livePackets'], 99)
            self.assertIn('最终核对', reports[30]['warning'])


class RuntimePortTests(unittest.TestCase):
    """Channels that pick their game port at runtime must still be decoded."""
    def frame(self,msg_id,body=b'',flag=0):
        # Frame header length is big-endian, matching HEADER_STRUCT in the decoder.
        import struct
        head=net_pb2.PacketHead(msg_id=msg_id,seq_id=1,packet_id=1,flag=flag,body_len=len(body))
        raw=head.SerializeToString()
        return struct.pack('>H',len(raw))+raw+body
    def setUp(self):
        import sys
        tool=Path(__file__).resolve().parent/'backup-tool'
        sys.path.insert(0,str(tool))
        sys.path.insert(0,str(tool/'proto_gen'))
        global net_pb2
        import net_pb2
    def test_non_game_bytes_are_not_a_game_stream(self):
        import parse_pcap as decoder
        self.assertFalse(decoder.looks_like_game_stream(b''))
        self.assertFalse(decoder.looks_like_game_stream(b'\xff\xff\xff\xff'))
    def test_pick_directions_prefers_parsable_side(self):
        import parse_pcap as decoder
        good=self.frame(1001,b'\x08\x01')
        self.assertEqual(decoder.pick_directions(b'GET / HTTP/1.1\r\n\r\n',good)[1][0],'s2c')
        self.assertEqual(decoder.pick_directions(good,b'HTTP')[0][0],'s2c')
    def test_pick_directions_keeps_both_sides(self):
        import parse_pcap as decoder
        self.assertEqual([d[0] for d in decoder.pick_directions(b'\x00\x00',b'\x00\x00')],['c2s','s2c'])

if __name__=='__main__':unittest.main()
