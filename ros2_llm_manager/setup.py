"""Package setup for ros2_llm_manager (ament_python build)."""

import os
from glob import glob
from setuptools import find_packages, setup

package_name = "ros2_llm_manager"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
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
    install_requires=[
        "setuptools==79.0.1",
        "httpx==0.28.1",
        "google-genai==1.74.0",
    ],
    zip_safe=True,
    maintainer="aquintan4",
    maintainer_email="aquintana.camacho@proton.me",
    description="ROS2 node for multi-provider LLM inference. Supports local models via Ollama and cloud models via Google Gemini.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "llm_manager_node = ros2_llm_manager.llm_manager_node:main",
            "llm_cli_client   = ros2_llm_manager.llm_cli_client:main",
        ],
    },
)
