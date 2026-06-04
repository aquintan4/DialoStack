"""Tkinter front-end for triggering pose saves.

Provides a small window to type a pose name and publish it on
/save_pose_trigger; mirrors names received on /selected_pose_name back into
the entry field.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String
import tkinter as tk


class GuiTrigger(Node):
    def __init__(self, entry_widget):
        super().__init__("gui_trigger")
        self.entry = entry_widget
        qos_profile = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher_ = self.create_publisher(String, "/save_pose_trigger", qos_profile)
        self.sub_ = self.create_subscription(String, "/selected_pose_name", self.name_callback, 10)

    def name_callback(self, msg):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, msg.data)

    def publish_pose_name(self, pose_name):
        if pose_name.strip():
            msg = String()
            msg.data = pose_name.strip()
            self.publisher_.publish(msg)


def main(args=None):
    rclpy.init(args=args)

    root = tk.Tk()
    root.title("NAO Pose Manager")
    root.geometry("300x130")

    label = tk.Label(root, text="Pose name:")
    label.pack(pady=10)

    entry = tk.Entry(root, width=30)
    entry.pack(pady=5)

    node = GuiTrigger(entry)

    def on_save():
        pose_name = entry.get()
        node.publish_pose_name(pose_name)

    btn = tk.Button(root, text="Save Pose", command=on_save)
    btn.pack(pady=5)

    def ros_spin():
        rclpy.spin_once(node, timeout_sec=0.01)
        root.after(10, ros_spin)

    root.after(10, ros_spin)

    def on_closing():
        node.destroy_node()
        rclpy.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
