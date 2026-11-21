import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from local_app.store import Store
from local_app.manager import Manager,profile_settings
from local_app.server import create_server

class LibraryTests(unittest.TestCase):
    def test_finished_flight_is_added_to_its_room(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);manager=Manager(store)
            # Stop the background poller so this test controls the finish boundary.
            manager.closing=True;manager.thread.join(timeout=3)
            room=store.room('Flight test');profile=store.profile('Test');runtime=Path(directory)/'runtime';runtime.mkdir()
            log=Path(directory)/'launcher.log';log.write_text('finished')
            with store.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('session',room['id'],profile['id'],None,'live','stopping',str(runtime),str(log),0,None,None))
            bag=Path(directory)/'flight';bag.mkdir();(bag/'metadata.yaml').write_text('test')
            manager.active='session';manager.destination=bag;manager.process=Mock(returncode=0)
            with patch.object(manager,'rebuild'):manager.finalize()
            self.assertIsNone(manager.active)
            self.assertEqual(store.one('sessions','session')['state'],'finished')
            records=store.rows('SELECT * FROM recordings WHERE room_id=?',(room['id'],))
            self.assertEqual(len(records),1);self.assertEqual(records[0]['linked'],0)
            self.assertEqual(store.one('sessions','session')['recording_id'],records[0]['id'])
    def test_persistence_and_recording_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);p=store.profile('Shadib');self.assertEqual(store.profile('shadib')['id'],p['id'])
            room=store.room('Robotics classroom');other=store.room('Kitchen')
            bag=Path(directory)/'bag';bag.mkdir();(bag/'metadata.yaml').write_text('test')
            record=store.recording(room['id'],bag)
            self.assertTrue(bag.exists());self.assertEqual(Store(directory).one('recordings',record['id'])['path'],str(bag.resolve()))
            alias=Path(directory)/'bag-alias';alias.symlink_to(bag.resolve(),target_is_directory=True)
            self.assertEqual(store.recording(room['id'],alias)['id'],record['id'])
            with self.assertRaises(ValueError):store.recording(other['id'],alias)
    def test_profile_and_command_selection(self):
        with patch('local_app.manager.platform.system',return_value='Darwin'),patch('local_app.manager.platform.machine',return_value='arm64'):
            self.assertIn(profile_settings('Nahil')['depth_model'],{'depth-anything','metric-indoor'})
            self.assertIn(profile_settings('Rian')['depth_model'],{'depth-anything','metric-indoor'})
        with patch('local_app.manager.platform.machine',return_value='x86_64'):
            self.assertIn(profile_settings('Nahil')['depth_model'],{'midas','metric-indoor'})
        with tempfile.TemporaryDirectory() as directory:
            manager=Manager(Store(directory))
            try:
                self.assertIsNone(manager.state())
                cmd,_=manager.command({'name':'Shadib'},'replay',Path(directory),recording='/test/bag')
                self.assertIn('--slam-all-frames',cmd);self.assertIn('--vision',cmd);self.assertNotIn('--enable-flight',cmd)
                self.assertEqual(cmd[cmd.index('--domain-id')+1],'73')
                with self.assertRaises(ValueError):manager.start(manager.store.room('Test')['id'],manager.store.profile('Test')['id'],'live')
            finally:manager.close()
    def test_http_idle_and_token_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            server=create_server(0,directory);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base+'/api/state') as response:state=json.load(response)
                self.assertIsNone(state['active']);self.assertEqual(state['rooms'],[])
                with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/api/rooms',data=b'{"name":"Test"}'))
                self.assertEqual(error.exception.code,403)
                req=Request(base+'/api/rooms',data=b'{"name":"Test"}',headers={'X-App-Token':server.token,'Content-Type':'application/json'})
                with urlopen(req) as response:self.assertEqual(json.load(response)['name'],'Test')
                with self.assertRaises(HTTPError):urlopen(base+'/api/room-map/../library.sqlite3')
            finally:server.shutdown();server.manager.close();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
