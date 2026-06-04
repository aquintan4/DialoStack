"""ament_python package definition for the ros2_dialog_manager package."""

import os
from glob import glob
from setuptools import find_packages, setup

package_name = "ros2_dialog_manager"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob(os.path.join("config", "*.yaml"))),
        (os.path.join("share", package_name, "launch"), glob(os.path.join("launch", "*.py"))),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="aquintan",
    maintainer_email="tu_correo@ejemplo.com",
    description="Dialog Manager (FSM + NLU/NLG) for ROS 2",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "dialog_manager_node = ros2_dialog_manager.dialog_manager_node:main",
        ],
    },
)
