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

int main(int argc, char** argv) {
    const bool ordered = argc == 3 && std::string(argv[1]) == "--ordered-input";
    if (argc != 1 && !ordered) {
        std::cerr << "Usage: tello_live_slam [--ordered-input PATH]\n";
        return 2;
    }
    const std::string input_path = ordered ? argv[2] : "live/frame.bin";
    std::signal(SIGINT, stop);
    std::signal(SIGTERM, stop);
    fs::create_directories("live");
    auto cfg = std::make_shared<stella_vslam::config>(
        "assets/tello_320_dense.yaml");
    stella_vslam::system slam(cfg, "assets/orb_vocab.fbow");
    slam.startup();
    double previous = -1, last_export = 0;
    std::streamoff offset = 0;
    size_t processed_frames = 0;
    double last_progress = 0, feed_seconds = 0;
    auto progress = [&]() {
        const double wall = now_seconds();
        if (wall - last_progress < 0.5) return;
        last_progress = wall;
        size_t expected = 0;
        std::ifstream finished("live/slam-input.done");
        const bool has_end = bool(finished >> expected);
        const bool complete = ordered && has_end && processed_frames >= expected;
        std::ofstream output("live/slam-status.tmp");
        output << "{\"timestamp\":" << std::setprecision(16) << wall
               << ",\"ordered\":" << (ordered ? "true" : "false")
               << ",\"processed_frames\":" << processed_frames
               << ",\"expected_frames\":" << expected
               << ",\"last_feed_seconds\":" << feed_seconds
               << ",\"state\":" << std::quoted(complete ? "finished" : "processing") << "}";
        output.close();
        fs::rename("live/slam-status.tmp", "live/slam-status.json");
    };
    std::cout << "Waiting for live ROS frames. Ctrl+C stops SLAM.\n";

    try {
        while (!stopped) {
            std::ifstream input(input_path, std::ios::binary);
            if (ordered) input.seekg(offset);
            double timestamp = 0;
            uint32_t width = 0, height = 0;
            input.read(reinterpret_cast<char*>(&timestamp), 8);
            input.read(reinterpret_cast<char*>(&width), 4);
            input.read(reinterpret_cast<char*>(&height), 4);
            const double now = now_seconds();

            if (!input || width != 320 || height != 240 ||
                (!ordered && (timestamp <= previous || now - timestamp > 2 ||
                timestamp > now + 1))) {
                progress();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            cv::Mat frame(240, 320, CV_8UC3);
            input.read(reinterpret_cast<char*>(frame.data), 320*240*3);
            if (!input) {
                progress();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }
            previous = timestamp;
            const auto feed_start = std::chrono::steady_clock::now();
            slam.feed_monocular_frame(frame, timestamp);
            feed_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now()-feed_start).count();
            ++processed_frames;
            if (ordered) offset += 16 + 320*240*3;
            progress();

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
                   << "{\"timestamp\":" << (ordered ? now : timestamp)
                   << ",\"frame_timestamp\":" << timestamp
                   << ",\"processed_frames\":" << processed_frames
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
