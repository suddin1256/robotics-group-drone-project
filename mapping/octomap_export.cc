#include <octomap/octomap.h>
#include <fstream>
#include <iostream>
#include <cmath>
// Input: frame_id origin_x origin_y origin_z endpoint_x endpoint_y endpoint_z.
// A scan is inserted once per frame, so dense pixels do not multiply votes.
int main(int argc,char** argv) {
    if(argc!=4)return 2;
    const double resolution=std::stod(argv[1]);
    if(!std::isfinite(resolution)||resolution<=0)return 2;
    octomap::OcTree tree(resolution);std::ifstream input(argv[2]);
    if(!input)return 3;
    octomap::Pointcloud scan;octomap::point3d origin;int frame=-1,id;double ox,oy,oz,x,y,z;
    while(input>>id>>ox>>oy>>oz>>x>>y>>z) {
        if(!std::isfinite(ox+oy+oz+x+y+z))continue;
        if(id!=frame){if(scan.size())tree.insertPointCloud(scan,origin,-1,true,true);scan.clear();frame=id;origin=octomap::point3d(ox,oy,oz);}
        scan.push_back(x,y,z);
    }
    if(scan.size())tree.insertPointCloud(scan,origin,-1,true,true);
    tree.updateInnerOccupancy();tree.prune();
    if(!tree.write(argv[3]))return 4;
    std::cout<<"Exported tentative OctoMap: "<<tree.size()<<" nodes. Scale and clearance unverified.\n";
    return 0;
}
