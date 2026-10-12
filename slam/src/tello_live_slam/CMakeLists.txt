cmake_minimum_required(VERSION 3.16)
project(tello_live_slam LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(stella_vslam REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgcodecs)
add_executable(tello_live_slam main.cc)
target_link_libraries(tello_live_slam PRIVATE
    stella_vslam::stella_vslam ${OpenCV_LIBS})
target_include_directories(tello_live_slam PRIVATE ${OpenCV_INCLUDE_DIRS})
