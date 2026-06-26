# Full NAO on-board bring-up for the clinical demo. Run THIS on the NAO instead
# of nao_min.launch.py when you need the robot STANDING.
#
# It restores the proven standing/posture stack from the old nao.launch.py (the
# robot stands up at boot via the leg swing and holds it), and adds DialoStack's
# audio bridge -- but WITHOUT simple_hri / sound_play, whose audio nodes would
# fight the bridge for the NAO microphone and speaker.
#
# Standing stack:
#   lola_client, nao_ik, nao_phase_provider, walk, mode_switcher_nao,
#   robot description, swing_launch (auto-runs 'only_legs_fast' -> legs stand),
#   nao_pos_action_server (posture).
# Audio: audio_bridge_node (mic -> /audio_in, /audio_out -> speaker).
#
# The arm gestures and eye LEDs come from the LAPTOP (arm_gesture_manager /
# eye_led_feedback), publishing straight to /effectors/*.
#
# Prerequisite: ws_rodrigo (nao_ros2, walk, nao_ik, nao_pos_server, ...) built on
# the NAO, plus the speech_io + ros2_dialog_interfaces overlay.

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        # LoLA bridge (gateway to motors/sensors).
        Node(
            package='nao_lola_client',
            executable='nao_lola_client',
            name='lola_node',
            output='screen',
        ),
        # Standing / balance stack.
        Node(package='nao_ik', executable='nao_ik', name='nao_ik'),
        Node(
            package='nao_phase_provider',
            executable='nao_phase_provider',
            name='nao_phase_provider',
            remappings=[('fsr', '/sensors/fsr')],
        ),
        Node(package='walk', executable='walk', name='walk'),
        Node(
            package='nao_ros2',
            executable='mode_switcher_nao',
            name='mode_switcher_nao',
            output='screen',
            shell=True,
        ),
        # Robot description (TF from joint states).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                FindPackageShare('nao_ros2'), '/launch/nao_description_launch.py'
            ])
        ),
        # Leg posture: swing_launch auto-publishes 'only_legs_fast' at boot, which
        # stands the legs up and holds them (this is what makes the NAO stand).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                FindPackageShare('nao_pos_server'), '/launch', '/swing_launch.py'
            ])
        ),
        # General posture action server.
        Node(
            package='nao_pos_server',
            executable='nao_pos_action_server',
            name='nao_pos_action_server',
            output='screen',
        ),
        # No camera here on purpose: the exercises are demonstration-only (the NAO
        # strikes the pose and holds it while speaking), with no pose detection.
        # Dropping usb_cam/camera_conversion also frees the NAO CPU and WiFi, which
        # keeps /audio_in clean and the transcription reliable.
        # DialoStack audio bridge (replaces simple_hri / sound_play).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                FindPackageShare('speech_io'), '/launch/audio_bridge.launch.py'
            ])
        ),
    ])
