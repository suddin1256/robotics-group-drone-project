#include <stella_vslam/system.h>
#include <stella_vslam/config.h>
#include <stella_vslam/publish/frame_publisher.h>
#include <stella_vslam/publish/map_publisher.h>
#include <stella_vslam/data/landmark.h>
#include <stella_vslam/data/keyframe.h>
#include <opencv2/imgcodecs.hpp>
#include <chrono>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <thread>
#include <vector>

namespace fs = std::filesystem;
volatile std::sig_atomic_t stopped = 0;
void stop(int) { stopped = 1; }

double now_seconds() {
    return std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

int main() {
    std::signal(SIGINT, stop);
    std::signal(SIGTERM, stop);
    fs::create_directories("live");
    auto cfg = std::make_shared<stella_vslam::config>(
        "assets/tello_320_dense.yaml");
    stella_vslam::system slam(cfg, "assets/orb_vocab.fbow");
    slam.startup();
    double previous = -1, last_export = 0;
    std::cout << "Waiting for live ROS frames. Ctrl+C stops SLAM.\n";

    try {
        while (!stopped) {
            std::ifstream input("live/frame.bin", std::ios::binary);
            double timestamp = 0;
            uint32_t width = 0, height = 0;
            input.read(reinterpret_cast<char*>(&timestamp), 8);
            input.read(reinterpret_cast<char*>(&width), 4);
            input.read(reinterpret_cast<char*>(&height), 4);
            const double now = now_seconds();

            if (!input || width != 320 || height != 240 ||
                timestamp <= previous || now - timestamp > 2 ||
                timestamp > now + 1) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            cv::Mat frame(240, 320, CV_8UC3);
            input.read(reinterpret_cast<char*>(frame.data), 320*240*3);
            if (!input) continue;
            previous = timestamp;
            slam.feed_monocular_frame(frame, timestamp);

            if (now - last_export < 1) continue;
            last_export = now;

            auto publisher = slam.get_map_publisher();
            std::vector<std::shared_ptr<stella_vslam::data::landmark>> points;
            std::set<std::shared_ptr<stella_vslam::data::landmark>> local;
            std::vector<std::shared_ptr<stella_vslam::data::keyframe>> cameras;
            publisher->get_landmarks(points, local);
            publisher->get_keyframes(cameras);
            const auto state = slam.get_frame_publisher()->get_tracking_state();

            std::ofstream output("live/map.tmp");
            output << std::setprecision(16)
                   << "{\"timestamp\":" << timestamp
                   << ",\"state\":" << std::quoted(state)
                   << ",\"points\":[";
            bool first = true;
            for (auto& point : points) {
                if (point->will_be_erased()) continue;
                const auto p = point->get_pos_in_world();
                if (!p.allFinite()) continue;
                if (!first) output << ",";
                first = false;
                output << "[" << p(0) << "," << p(1) << "," << p(2) << "]";
            }
            output << "],\"cameras\":[";
            first = true;
            for (auto& camera : cameras) {
                if (camera->will_be_erased()) continue;
                const auto p = camera->get_trans_wc();
                if (!p.allFinite()) continue;
                if (!first) output << ",";
                first = false;
                output << "[" << p(0) << "," << p(1) << "," << p(2) << "]";
            }
            output << "]}";
            output.close();
            fs::rename("live/map.tmp", "live/map.json");

            const auto annotated = slam.get_frame_publisher()->draw_frame();
            if (!annotated.empty()) {
                cv::imwrite("live/preview.tmp.jpg", annotated);
                fs::rename("live/preview.tmp.jpg", "live/preview.jpg");
            }
            std::cout << state << " | keyframes: " << cameras.size()
                      << " | landmarks: " << points.size() << std::endl;
        }
    } catch (const std::exception& error) {
        std::cerr << "Live SLAM error: " << error.what() << std::endl;
        slam.shutdown();
        return 1;
    }

    slam.shutdown();
    slam.save_map_database("live/session.msg");
    std::cout << "Saved live/session.msg\n";
}
