import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from local_app.store import Store
from local_app.manager import Manager
from local_app.recordings import scan,inventory,permanently_delete

class RecordingLibraryTests(unittest.TestCase):
    def test_incomplete_bag_can_be_catalogued_and_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bag=root/'unfinished';bag.mkdir();(bag/'flight_0.mcap').write_bytes(b'fixture')
            store=Store(root/'library');self.assertEqual(scan(store,root),1)
            record=inventory(store)[0];self.assertTrue(record['incomplete']);self.assertFalse(record['missing'])
            permanently_delete(store,record['id'],record['name']);self.assertFalse(bag.exists())
    def bag(self,folder,name='flight_test'):
        path=Path(folder)/name;path.mkdir();(path/'metadata.yaml').write_text('duration:\n  nanoseconds: 125000000000\n')
        (path/(name+'_0.mcap')).write_bytes(b'fixture recording');return path
    def test_scan_and_assignment_preserve_original_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);bag=self.bag(folder);store=Store(folder/'library');room=store.room('Classroom')
            self.assertEqual(scan(store,folder),1);record=inventory(store)[0]
            self.assertIsNone(record['room_id']);self.assertEqual(record['duration_seconds'],125)
            store.assign_recording(record['id'],room['id']);self.assertEqual(scan(store,folder),0)
            self.assertEqual(inventory(store)[0]['room_name'],'Classroom')
            store.assign_recording(record['id'],None);self.assertTrue((bag/'metadata.yaml').exists())
            self.assertIsNone(inventory(store)[0]['room_id'])
    def with_capture(self,store,record,room):
        key='session';runtime=store.root/'rooms'/room['id']/'sessions'/key/'runtime';runtime.mkdir(parents=True)
        (runtime/'derived.txt').write_text('derived');capture=store.root/'rooms'/room['id']/'maps'/'capture';capture.mkdir(parents=True)
        (capture/'map.json').write_text('{"points":[[1,2,3]]}')
        with store.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,room['id'],'profile',record['id'],'replay','finished',str(runtime),str(runtime.parent/'log'),0,0,None))
            db.execute('INSERT INTO maps VALUES(?,?,?,?,?,?,?,?)',('capture',room['id'],key,'origin',str(capture),0,1,'Tracking'))
        return runtime,capture
    def test_unlink_moves_capture_and_relink_preserves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bag=self.bag(root);store=Store(root/'library');a=store.room('A');b=store.room('B');record=store.recording(a['id'],bag)
            runtime,capture=self.with_capture(store,record,a)
            store.assign_recording(record['id'],None)
            self.assertFalse(capture.exists());self.assertTrue((store.root/'unassigned/maps/capture/map.json').exists())
            self.assertIsNone(store.one('maps','capture')['room_id']);self.assertTrue(runtime.exists());self.assertTrue(bag.exists())
            store.assign_recording(record['id'],b['id'])
            self.assertTrue((store.root/'rooms'/b['id']/'maps/capture/map.json').exists())
            self.assertEqual(store.one('sessions','session')['room_id'],b['id'])
    def test_permanent_delete_requires_name_and_removes_only_selected_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bag=self.bag(root);other=self.bag(root,'other');store=Store(root/'library');room=store.room('A');record=store.recording(room['id'],bag)
            runtime,capture=self.with_capture(store,record,room)
            with self.assertRaises(ValueError):permanently_delete(store,record['id'],'wrong name')
            self.assertTrue(bag.exists());self.assertTrue(runtime.exists())
            permanently_delete(store,record['id'],record['name'])
            self.assertFalse(bag.exists());self.assertFalse(runtime.parent.exists());self.assertFalse(capture.exists());self.assertTrue(other.exists())
            self.assertEqual(store.rows('SELECT * FROM recordings'),[]);self.assertEqual(store.rows('SELECT * FROM maps'),[])
    def test_outside_derived_path_rejected_before_deleting_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bag=self.bag(root);store=Store(root/'library');room=store.room('A');record=store.recording(room['id'],bag)
            runtime,_=self.with_capture(store,record,room)
            with store.connect() as db:db.execute('UPDATE sessions SET runtime=?',(str(root/'outside/session/runtime'),))
            with self.assertRaises(ValueError):permanently_delete(store,record['id'],record['name'])
            self.assertTrue(bag.exists());self.assertTrue(runtime.exists())
    def test_preview_without_room_can_be_assigned_while_playing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bag=self.bag(root);store=Store(root/'library');record=store.recording(None,bag);profile=store.profile('Shadib');room=store.room('Classroom')
            manager=Manager(store);manager.closing=True;manager.thread.join(timeout=3)
            process=Mock(returncode=0);process.poll.return_value=None
            try:
                with patch('local_app.manager.subprocess.Popen',return_value=process) as launch:
                    active=manager.start(None,profile['id'],'replay',record['id'],quick=True)
                    self.assertIsNone(active['room_id']);self.assertIn('--no-slam',launch.call_args.args[0]);self.assertNotIn('--enable-flight',launch.call_args.args[0])
                    manager.manage_recording('assign',record['id'],room['id'])
                    self.assertEqual(manager.state()['room_id'],room['id'])
                    with self.assertRaises(ValueError):manager.manage_recording('delete',record['id'],confirmation=record['name'])
                    self.assertTrue(bag.exists())
            finally:
                process.poll.return_value=0
                with patch.object(manager,'rebuild'):manager.close()

if __name__=='__main__':unittest.main()
