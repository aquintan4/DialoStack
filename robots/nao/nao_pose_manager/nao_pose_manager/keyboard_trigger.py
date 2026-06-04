"""Keyboard front-end for triggering pose saves.

Reads single keypresses from the terminal and publishes auto-numbered pose
names on /save_pose_trigger ('s' to save, 'q' to quit).
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String
import sys
import select
import termios
import tty


class KeyboardTrigger(Node):
    def __init__(self):
        super().__init__("keyboard_trigger")
        qos_profile = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher_ = self.create_publisher(String, "/save_pose_trigger", qos_profile)
        self.settings = termios.tcgetattr(sys.stdin)

    def get_key(self):
        tty.setraw(sys.stdin.fileno())
        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if rlist:
            key = sys.stdin.read(1)
        else:
            key = ""
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
        return key

    def run(self):
        print("Press 's' to save the current pose, 'q' to quit:")
        pose_count = 1

        while rclpy.ok():
            key = self.get_key()
            if key == "s":
                msg = String()
                msg.data = f"pose_{pose_count}"
                self.publisher_.publish(msg)
                print(f"Save command sent: pose_{pose_count}")
                pose_count += 1
            elif key == "q":
                break


def main(args=None):
    rclpy.init(args=args)
    node = KeyboardTrigger()
    node.run()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
