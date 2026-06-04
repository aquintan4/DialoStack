"""Tkinter tool to preview saved poses in simulation.

Lists the poses from nao_saved_poses.yaml as buttons; clicking one publishes
it on /pose_tester_joints (for RViz/joint_state_publisher_gui) and its name on
/selected_pose_name.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
import yaml
import os
import tkinter as tk


class PoseTester(Node):
    def __init__(self):
        super().__init__("pose_tester")
        self.publisher_ = self.create_publisher(JointState, "/pose_tester_joints", 10)
        self.name_publisher_ = self.create_publisher(String, "/selected_pose_name", 10)
        self.poses = self.load_poses()

    def load_poses(self):
        file_path = "nao_saved_poses.yaml"
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def publish_pose(self, pose_name):
        self.poses = self.load_poses()
        if pose_name not in self.poses:
            return

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        pose_data = self.poses[pose_name]

        msg.name = list(pose_data.keys())
        msg.position = [float(val) for val in pose_data.values()]
        self.publisher_.publish(msg)

        name_msg = String()
        name_msg.data = pose_name
        self.name_publisher_.publish(name_msg)


def main(args=None):
    rclpy.init(args=args)
    node = PoseTester()

    root = tk.Tk()
    root.title("NAO Pose Tester")
    root.geometry("300x500")

    top_frame = tk.Frame(root)
    top_frame.pack(fill=tk.X, pady=5)

    label = tk.Label(top_frame, text="Select a pose to apply:")
    label.pack()

    canvas = tk.Canvas(root)
    scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux_up(event):
        canvas.yview_scroll(-1, "units")

    def _on_mousewheel_linux_down(event):
        canvas.yview_scroll(1, "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    canvas.bind_all("<Button-4>", _on_mousewheel_linux_up)
    canvas.bind_all("<Button-5>", _on_mousewheel_linux_down)

    def populate_buttons():
        for widget in scrollable_frame.winfo_children():
            widget.destroy()

        node.poses = node.load_poses()
        for pose_name in node.poses.keys():
            btn = tk.Button(
                scrollable_frame,
                text=pose_name,
                width=25,
                command=lambda p=pose_name: node.publish_pose(p),
            )
            btn.pack(pady=2, padx=10)

    btn_refresh = tk.Button(
        top_frame, text="↻ Refresh / Reload YAML", command=populate_buttons, bg="lightblue"
    )
    btn_refresh.pack(pady=5)

    populate_buttons()

    def on_closing():
        node.destroy_node()
        rclpy.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
