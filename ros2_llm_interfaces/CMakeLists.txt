cmake_minimum_required(VERSION 3.8)
project(ros2_llm_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/LlmError.msg"
  "srv/CreateSession.srv"
  "srv/DeleteSession.srv"
  "srv/ListSessions.srv"
  "action/LlmInference.action"
  DEPENDENCIES action_msgs
)

ament_package()