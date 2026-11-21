"""Start TelloTubby, the local room-library app. No hardware or ROS starts until selected in the UI."""
import argparse,threading,webbrowser
from local_app.server import create_server

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8000);p.add_argument('--no-browser',action='store_true');p.add_argument('--data-dir');args=p.parse_args()
    server=create_server(args.port,args.data_dir);url=f'http://127.0.0.1:{server.server_port}'
    print(f'TelloTubby: {url}\nNo drone connection started. Library: {server.store.root}',flush=True)
    if not args.no_browser:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:print('Closing app. A running session will be asked to stop; land before closing.',flush=True)
    finally:server.manager.close();server.server_close()

if __name__=='__main__':main()
