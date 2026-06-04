import os
from glob import glob

from setuptools import setup

package_name = "vision_io"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        (
            "share/" + package_name,
            ["package.xml"],
        ),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.py"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="aquintan4",
    maintainer_email="aquintana.camacho@proton.me",
    description="Camera-agnostic vision input package for ROS 2, providing emotion detection and lip activity detection nodes.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "emotion_detector = vision_io.emotion_detector:main",
            "lip_activity_detector = vision_io.lip_activity_detector:main",
        ],
    },
)
