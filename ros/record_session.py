"""ROS CLI entry point with the local community message overlay loaded."""
from community_paths import configure
configure()
from ros2cli.cli import main
if __name__=='__main__':
    main()
