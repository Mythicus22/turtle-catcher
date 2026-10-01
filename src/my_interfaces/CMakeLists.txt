cmake_minimum_required(VERSION 3.8)
project(my_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(service_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "src/Turtle.msg"
  "src/TurtleArray.msg"
  "src/CatchTurtle.srv"
  DEPENDENCIES service_msgs
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()
