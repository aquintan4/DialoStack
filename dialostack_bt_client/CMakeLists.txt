cmake_minimum_required(VERSION 3.8)
project(dialostack_bt_client)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(ros2_dialog_interfaces REQUIRED)

set(deps rclcpp rclcpp_action behaviortree_cpp ros2_dialog_interfaces)

include_directories(include)

# The leaf node as a BT.CPP plugin, loadable at runtime via registerFromPlugin().
add_library(dialostack_bt_client_plugin SHARED
  src/execute_dialog.cpp
  src/bt_plugins.cpp
)
ament_target_dependencies(dialostack_bt_client_plugin ${deps})

# Generic runner: loads a tree XML and ticks it.
add_executable(bt_runner src/bt_runner.cpp)
target_link_libraries(bt_runner dialostack_bt_client_plugin)
ament_target_dependencies(bt_runner ${deps})

install(TARGETS dialostack_bt_client_plugin
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(TARGETS bt_runner DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})

ament_export_include_directories(include)
ament_package()
