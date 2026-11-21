import importlib.util,json,signal,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from local_app.store import Store
from local_app.manager import Manager
from scripts.build_room import fingerprint

class BackgroundRoomTests(unittest.TestCase):
    def test_batch_is_exclusive_and_cancel_targets_its_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);room=store.room('Room');profile=store.profile('Shadib')
            bag=Path(directory)/'bag';bag.mkdir();(bag/'metadata.yaml').write_text('test');store.recording(room['id'],bag)
            manager=Manager(store);manager.closing=True;manager.thread.join(timeout=3)
            process=Mock(pid=12345);process.poll.return_value=None
            try:
                with patch.object(manager,'mapping_setup_state',return_value={'ready':True}),patch('local_app.manager.subprocess.Popen',return_value=process) as launch:
                    result=manager.start_room_build(room['id'],profile['id'])
                    self.assertEqual(result['state'],'queued')
                    command=launch.call_args.args[0];self.assertTrue(any('build_room.py' in x for x in command));self.assertNotIn('--enable-flight',command)
                    with self.assertRaises(ValueError):manager.start(room['id'],profile['id'],'replay')
                    with self.assertRaises(ValueError):manager.start_room_build(room['id'],profile['id'])
                    with patch('local_app.manager.os.killpg') as kill:
                        manager.cancel_room_build(room['id']);kill.assert_called_once_with(12345,signal.SIGINT)
                process.poll.return_value=0
                self.assertEqual(manager.room_build_state(room['id'])['state'],'interrupted')
            finally:manager.batch_process=None;manager.close()
    def test_recording_changes_invalidate_cached_work(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'metadata.yaml').write_text('one');first=fingerprint(folder)
            (folder/'recording.mcap').write_bytes(b'changed');self.assertNotEqual(first,fingerprint(folder))

if __name__=='__main__':unittest.main()
