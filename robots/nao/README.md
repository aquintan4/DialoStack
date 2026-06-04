# robots/nao — NAO embodiment layer

Optional robot-embodiment layer for the SoftBank NAO. It contains the robot model
(`nao_description`) and the pose/gesture/LED tooling (`nao_pose_manager`). This layer is
a pure consumer of the dialog stack's signals: the dialogue core has no NAO dependency
and runs unchanged without it. These nodes only subscribe to `/is_speaking`, `/user_vad`
and `/target_pose` and drive the robot accordingly.

See [../../docs/architecture.md](../../docs/architecture.md) for the full design.

## Packages

- **nao_description** — URDF and RViz config for the NAO V40, plus a sim bringup.
- **nao_pose_manager** — pose capture, playback, gesture managers and eye-LED feedback.

> **Note on meshes:** the NAO 3D meshes are licensed by SoftBank Robotics and cannot be
> redistributed here (`meshes/` and `texture/` are git-ignored). To visualise the full
> model, install them with the official `nao_meshes` installer — see the setup steps in
> [`nao_description/README.md`](nao_description/README.md).

## Nodes (nao_pose_manager)

| Node (ros2 run name) | Description |
| --- | --- |
| `gesture_manager` | Simulation gesture FSM; publishes `JointState` to `/pose_tester_joints` for RViz. |
| `arm_gesture_manager` | Real-robot arm gesture FSM; drives nao_lola effector topics. |
| `eye_led_feedback` | Maps interaction state to NAO eye-LED colors. |
| `pose_saver` | Saves the live `/joint_states` pose to `nao_saved_poses.yaml` on trigger. |
| `pose_tester` | Tkinter tool to preview saved poses in simulation. |
| `keyboard_trigger` / `gui_trigger` | Terminal / GUI front-ends that publish pose-save names. |

## Interfaces

| Name | Type | Direction |
| --- | --- | --- |
| `/is_speaking` | `std_msgs/Bool` | subscribe (gesture, arm, led) |
| `/user_vad` | `std_msgs/Float32` | subscribe (eye_led_feedback) |
| `/target_pose` | `std_msgs/String` | subscribe (gesture, arm) |
| `/pose_tester_joints` | `sensor_msgs/JointState` | publish (sim gesture, tester) |
| `/save_pose_trigger` | `std_msgs/String` | publish (triggers) / subscribe (saver) |
| `/selected_pose_name` | `std_msgs/String` | publish (tester) / subscribe (gui) |
| `/joint_states` | `sensor_msgs/JointState` | subscribe (pose_saver) |
| `/effectors/joint_positions`, `/effectors/joint_stiffnesses` | `nao_lola_command_msgs/*` | publish (arm) |
| `/effectors/left_eye_leds`, `/effectors/right_eye_leds` | `nao_lola_command_msgs/*` | publish (led) |

### External dependency

The real-robot nodes (`arm_gesture_manager`, `eye_led_feedback`) require
[`nao_lola_command_msgs`](https://github.com/ijnek/nao_lola) and a running nao_lola
bridge on the robot. The simulation path does not need it.

## Usage

Simulation (RViz + pose tooling, no robot):

```bash
ros2 launch nao_pose_manager nao_sim.launch.py
```

Real robot (arm gestures + eye LEDs, needs nao_lola running):

```bash
ros2 launch nao_pose_manager arm_gesture_manager.launch.py
```

### Pose capture workflow

1. Launch the sim: `ros2 launch nao_pose_manager nao_sim.launch.py`.
2. Pose the robot with the `joint_state_publisher_gui` sliders in RViz.
3. Type a pose name in the `gui_trigger` window (or press `s` in `keyboard_trigger`).
4. `pose_saver` writes the named pose into `config/nao_saved_poses.yaml`.
5. Preview saved poses by clicking them in the `pose_tester` window.

## Configuration

Saved poses and RViz views live in `nao_pose_manager/config/` (`nao_saved_poses.yaml`,
`config.rviz`); gesture timing/stiffness are launch arguments on
`arm_gesture_manager.launch.py`. See [../../docs/configuration.md](../../docs/configuration.md).
