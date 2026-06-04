"""Package setup for nao_pose_manager."""

import os
from glob import glob
from setuptools import find_packages, setup

package_name = "nao_pose_manager"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="aquintan",
    maintainer_email="aquintana.camacho@proton.me",
    description="Pose capture, playback, and gesture management nodes for the NAO robot.",
    license="MIT",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "pose_saver = nao_pose_manager.pose_saver:main",
            "keyboard_trigger = nao_pose_manager.keyboard_trigger:main",
            "gui_trigger = nao_pose_manager.gui_trigger:main",
            "pose_tester = nao_pose_manager.pose_tester:main",
            "gesture_manager = nao_pose_manager.gesture_manager:main",
            "arm_gesture_manager = nao_pose_manager.arm_gesture_manager:main",
            "eye_led_feedback = nao_pose_manager.eye_led_feedback:main",
        ],
    },
)
