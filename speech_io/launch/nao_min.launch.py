# Minimal NAO on-board bring-up for DialoStack. Run THIS on the NAO.
#
# It starts the only two things the robot needs locally for the dialogue stack:
#   - nao_lola_client : LoLA bridge (from the NAO's base workspace). Exposes
#                       /sensors/* and applies /effectors/*, so the laptop-side
#                       nodes (arm_gesture_manager, eye_led_feedback, ...) drive
#                       the robot directly.
#   - audio_bridge_node : DialoStack's audio bridge (this package). Captures the
#                         NAO mic to /audio_in and plays /audio_out on the NAO
#                         speaker over the AudioChunk contract.
#
# Everything heavy (Piper TTS, Whisper STT, the LLM, the dialog manager, the
# pose/LED managers and the behavior tree) runs on the LAPTOP.
#
# NOTE: this launch references nao_lola_client by name; it only resolves when the
# NAO's base workspace is sourced (it is, on the robot). On a non-NAO machine use
# audio_bridge.launch.py instead. speech_io declares no dependency on the NAO
# packages - this is an optional convenience bring-up.

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='nao_lola_client',
            executable='nao_lola_client',
            name='lola_node',
            output='screen',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                FindPackageShare('speech_io'), '/launch/audio_bridge.launch.py'
            ])
        ),
    ])
