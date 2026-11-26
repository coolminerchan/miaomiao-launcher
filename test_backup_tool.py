"""Synthetic backup tests: no live capture, account login or network access."""
from pathlib import Path
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backup-tool'))
import parse_pcap as parser
import extract_gardens as gardens
import net_pb2
import cramjam


def frame(msg_id, body, compressed=False):
    payload = bytes(cramjam.snappy.compress_raw(body)) if compressed else body
    head = net_pb2.PacketHead(msg_id=msg_id, body_len=len(payload), flag=int(compressed))
    header = head.SerializeToString()
    return struct.pack('>H', len(header)) + header + payload


class BackupTests(unittest.TestCase):
    def test_frames_snappy_and_truncation(self):
        data = frame(1006, b'example', True) + frame(1016, b'tail')
        packets, remaining = parser.parse_game_stream(data)
        self.assertEqual([p['body'] for p in packets], [b'example', b'tail'])
        self.assertEqual(remaining, 0)
        packets, remaining = parser.parse_game_stream(data[:-1])
        self.assertEqual(len(packets), 1)
        self.assertGreater(remaining, 0)

    def test_login_export_removes_known_secret_and_requests(self):
        login = net_pb2.PlayerLoginRsp(client_log_server_token='synthetic-secret')
        payload = frame(1001, b'synthetic-request') + frame(1004, login.SerializeToString())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'export'
            with patch.object(parser, 'prepare_capture', side_effect=lambda path: path), patch.object(parser, 'list_tcp_streams', return_value=[0]), patch.object(parser, 'follow_tcp_stream', return_value=('127.0.0.1:40000', '127.0.0.1:11003', b'', payload, [])), contextlib.redirect_stdout(io.StringIO()):
                parser.analyze_pcap(Path('synthetic.pcapng'), out)
            summary = json.loads((out / 'summary.json').read_text())
            self.assertEqual(summary['omitted_login_requests'], 1)
            self.assertEqual(summary['sanitized_login_responses'], 1)
            raw = list((out / 'raw').glob('*.bin'))
            self.assertEqual(len(raw), 1)
            self.assertFalse(net_pb2.PlayerLoginRsp.FromString(raw[0].read_bytes()).client_log_server_token)
            self.assertNotIn('synthetic-secret', ''.join(p.read_text() for p in (out / 'json').glob('*.json')))

    def test_tshark_bidirectional_reassembly_output(self):
        result = type('Result', (), {'returncode': 0, 'stderr': '', 'stdout': 'Node 0: 127.0.0.1:40000\nNode 1: 127.0.0.1:11003\n6162\n\t6364\n====\n'})()
        with patch.object(parser.subprocess, 'run', return_value=result):
            node0, node1, forward, backward = parser.extract_tcp_stream_directions(Path('synthetic.pcapng'), 0)
        self.assertEqual((forward, backward), (b'ab', b'cd'))

    def test_garden_only_exports_expected_scene(self):
        notice = net_pb2.SceneDataNotice()
        notice.data.scene_id = 9999
        notice.data.channel_id = 1000000
        notice.data.scene_garden_data.garden_furniture_info_map[1].SetInParent()
        payload = frame(1016, notice.SerializeToString())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(gardens, 'prepare_capture', side_effect=lambda path: path), patch.object(gardens, 'list_tcp_streams', return_value=[0]), patch.object(gardens, 'extract_tcp_stream_directions', return_value=('', '', b'', payload)), contextlib.redirect_stdout(io.StringIO()):
                gardens.extract_gardens(Path('synthetic.pcapng'), out)
            index = json.loads((out / 'gardens_index.json').read_text())
            self.assertEqual(len(index), 1)
            self.assertEqual(index[0]['owner_uid'], 1000000)
            self.assertEqual(index[0]['furniture_count'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
