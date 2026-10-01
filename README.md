# Turtle Catcher

A small ROS 2 game built on `turtlesim`, with autonomous and manual memory-game modes. New target turtles appear over time, up to a configurable limit.

## Features

- Autonomous target selection and pursuit
- Manual keyboard control with oldest-target memory gameplay
- Terminal scorecard and replay prompt for manual rounds
- Configurable choice between the closest target and the first reported target
- Random target spawning with configurable frequency and population limit
- Custom ROS 2 messages for tracking live turtles
- Custom ROS 2 service for requesting a catch
- Separate launch files for autonomous and manual play

## Requirements

- Ubuntu with ROS 2 Jazzy installed
- `turtlesim`
- `colcon`
- The ROS 2 package providing `service_msgs` (required by the interface package)

The workspace currently contains a VS Code configuration targeting ROS 2 Jazzy and Python 3.12.

## Packages

| Package | Purpose |
| --- | --- |
| `turtlesim_catch_them_all` | Python nodes that control the catcher and spawn/manage targets |
| `my_interfaces` | Custom messages and the catch service |
| `my_bringup` | XML launch file and game parameters |

## Build

From the workspace root:

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

If `rosdep` is not configured on your machine, install the dependencies listed in the requirements section with your normal ROS 2 package manager, then run the `colcon build` and `source` commands.

## Run the game

Choose one mode per terminal. Do not run both launch files at the same time because they use the same `turtle1`, topics, and services.

### Autonomous mode

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch my_bringup turtlesim_catch_them_all.launch.xml
```

The launch file starts:

1. `turtlesim_node`
2. `turtlesim_catch_them_all/controller`
3. `turtlesim_catch_them_all/spawner`

The game can also be started node-by-node after starting `turtlesim_node`, but the launch file is the recommended entry point because it applies the shared parameter file automatically.

### Manual memory mode

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch my_bringup manual_catch_them_all.launch.xml
```

Keep focus on the terminal running the launch command. The manual controller accepts single-key commands:

| Key | Action |
| --- | --- |
| `W` | Move forward |
| `S` | Move backward |
| `A` | Rotate left |
| `D` | Rotate right |
| `Space` | Stop |
| `Q` | End the current round |

Linear and angular input are independent: hold `W` and press/hold `A` or `D` to drive in a curve. Movement stops automatically when no repeat input is received for the configured `key_hold_timeout`; `Space` stops immediately.

The spawner continues to create targets, but their names are not printed in manual mode. The first target in the live-target list is the oldest target and must be caught first. Catching a newer target ends the round. Correct catches increase the terminal score. After a round ends, enter `y` to reset the catcher, clear the current targets, and start another round, or `n` to exit.

## How the game works

### Spawner

`turtle_spawner` creates targets at random positions and orientations inside the turtlesim arena. Each target is named using the configured prefix and an incrementing counter. The node keeps an in-memory list of live targets and publishes that list after every successful spawn or catch.

The default configuration is:

- Prefix: `my_turtle`
- Spawn frequency: `1.5` turtles per second
- Maximum live targets: `5`

### Controller

`turtle_controller` listens to `turtle1`'s pose and the live-target list. By default it chooses the closest target, turns toward it, and publishes velocity commands to move toward it. When the distance is at most `0.5`, it requests that target through the `catch_turtle` service. The controller also disables `turtle1`'s drawing pen once its first pose is received.

This is a proportional pursuit controller, not a path planner: it drives directly toward the target and does not avoid other turtles or obstacles.

## Configuration

Parameters are defined in `src/my_bringup/config/catch_them_all_config.yaml` and loaded by the launch file:

```yaml
/turtle_controller:
  ros__parameters:
    catch_closest_turtle_first: true
    max_linear_speed: 9.0

/manual_controller:
  ros__parameters:
    manual_linear_speed: 2.0
    manual_angular_speed: 2.5
    catch_distance: 0.5
    key_hold_timeout: 0.6

/turtle_spawner:
  ros__parameters:
    turtle_name_prefix: "my_turtle"
    spawn_frequency: 1.5
    max_alive_turtles: 5
```

To change the game, edit the YAML file and rebuild if needed before sourcing the workspace again. The controller parameter can be set to `false` to catch the first target in the published array instead of selecting the nearest one. `max_linear_speed` limits autonomous catcher velocity in turtlesim units per second. `manual_linear_speed`, `manual_angular_speed`, `catch_distance`, and `key_hold_timeout` control manual play. Because ordinary terminals provide keypresses rather than true key-release events, `key_hold_timeout` is the stop-after-release approximation.

You can also change the speed while the game is running:

```bash
ros2 param set /turtle_controller max_linear_speed 1.0
```

## ROS 2 interfaces

### Topics

| Name | Type | Direction | Purpose |
| --- | --- | --- | --- |
| `/turtle1/cmd_vel` | `geometry_msgs/msg/Twist` | Controller publishes | Velocity commands for the catcher |
| `/turtle1/pose` | `turtlesim/msg/Pose` | Controller subscribes | Current catcher pose |
| `/alive_turtles` | `my_interfaces/msg/TurtleArray` | Spawner publishes | Current target list |

### Services

| Name | Type | Owner | Purpose |
| --- | --- | --- | --- |
| `/catch_turtle` | `my_interfaces/srv/CatchTurtle` | Spawner | Request that a named target be removed |
| `/spawn` | `turtlesim/srv/Spawn` | turtlesim | Used by the spawner to create targets |
| `/kill` | `turtlesim/srv/Kill` | turtlesim | Used by the spawner to remove caught targets |
| `/turtle1/set_pen` | `turtlesim/srv/SetPen` | turtlesim | Used to disable the catcher trail |
| `/turtle1/teleport_absolute` | `turtlesim/srv/TeleportAbsolute` | turtlesim | Used to reset manual rounds |

The custom service is:

```text
string name
---
bool success
```

The custom messages are:

```text
# my_interfaces/msg/Turtle
string name
float64 x
float64 y
float64 theta

# my_interfaces/msg/TurtleArray
Turtle[] turtles
```

## Useful inspection commands

Run these in another sourced terminal while the game is active:

```bash
ros2 node list
ros2 topic list
ros2 topic echo /alive_turtles
ros2 topic echo /turtle1/pose
ros2 service list
ros2 interface show my_interfaces/msg/TurtleArray
ros2 interface show my_interfaces/srv/CatchTurtle
```

To inspect the current node parameters:

```bash
ros2 param list /turtle_controller
ros2 param list /turtle_spawner
```

## Tests and linting

The Python package includes the standard ROS 2 test layout for copyright, `flake8`, and `pep257` checks. Run the package tests with:

```bash
colcon test --packages-select turtlesim_catch_them_all
colcon test-result --verbose
```

## Troubleshooting

### Workspace was moved

`colcon` stores absolute paths in its generated CMake cache and install setup files. If this workspace is moved, a build can fail with a message such as `CMakeCache.txt ... is different than the directory ... where CMakeCache.txt was created`, or the nodes may fail to import `my_interfaces`.

From the workspace root, move or remove the generated directories and rebuild:

```bash
mv build build.stale
mv install install.stale
mv log log.stale
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

Also remove any old workspace `source .../install/setup.bash` line from your shell startup file. A fresh terminal should source the Jazzy installation and this workspace’s `install/setup.bash` only.

## Current limitations

- Manual mode has a score and round-ending rules, but no timed leaderboard or persistent high-score storage.
- Targets are selected from their recorded spawn coordinates; targets do not move autonomously.
- The controller does not perform obstacle avoidance or collision-aware path planning.
- Spawning is asynchronous. If the turtlesim spawn service is not ready, that spawn attempt is skipped.
- The default random spawn bounds are fixed in the spawner implementation to the turtlesim arena range of `0.0` to `11.0`.

## Project layout

```text
.
├── src/
│   ├── my_bringup/
│   │   ├── config/catch_them_all_config.yaml
│   │   └── launch/
│   │       ├── manual_catch_them_all.launch.xml
│   │       └── turtlesim_catch_them_all.launch.xml
│   ├── my_interfaces/
│   │   └── src/
│   │       ├── CatchTurtle.srv
│   │       ├── Turtle.msg
│   │       └── TurtleArray.msg
│   └── turtlesim_catch_them_all/
│       └── turtlesim_catch_them_all/
│           ├── manual_controller.py
│           ├── turtle_controller.py
│           └── turtle_spawner.py
├── build/
├── install/
└── log/
```

The `build/`, `install/`, and `log/` directories are generated by `colcon` and are not required to understand or modify the source packages.
