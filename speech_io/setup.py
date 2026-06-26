import os
from glob import glob

from setuptools import setup

package_name = "speech_io"

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
    description="Speech input/output package for ROS 2, including speech-to-text, text-to-speech, and interactive audio testing nodes.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "speech_to_text_node = speech_io.speech_to_text_node:main",
            "text_to_speech_node = speech_io.text_to_speech_node:main",
            "audio_bridge_node = speech_io.audio_bridge_node:main",
            "test_audio_node = speech_io.test_audio:main",
        ],
    },
)
