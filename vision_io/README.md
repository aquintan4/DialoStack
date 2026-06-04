# vision_io — optional camera-based perception for ROS 2

Camera-agnostic vision input. Adds two optional perception signals to the stack: facial
emotion recognition and visual lip-activity detection. Both consume a generic camera
image topic and are entirely optional — the dialog core runs without them.

See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Nodes

| Node (ros2 run name) | Description |
| --- | --- |
| `emotion_detector` | Detects a face and classifies emotion (Hugging Face pipeline); publishes JSON. |
| `lip_activity_detector` | Estimates speaking from lip-motion dynamics (MediaPipe FaceLandmarker). |

## Interfaces

| Name | Type | Direction |
| --- | --- | --- |
| `/camera/image_raw` | `sensor_msgs/Image` | subscribe (both nodes) |
| `/user_emotion` | `std_msgs/String` (JSON `{emotion, confidence, source}`) | publish (emotion) |
| `/user_speaking` | `std_msgs/Bool` | publish (lip) |
| `/lip_activity` | `std_msgs/Float32` (lip-gap ratio) | publish (lip) |

The camera topic is configurable (`input_topic` / `image_topic`, default
`/camera/image_raw`); point it at any image source. The lip detector classifies
speaking from the variance of lip-gap changes, which filters out yawns and smiles.

## Usage

```bash
ros2 launch vision_io emotion_detector.launch.py     # uses config/params.yaml
ros2 launch vision_io lip_detector.launch.py         # uses config/lip_activity_params.yaml
```

Or run directly:

```bash
ros2 run vision_io emotion_detector --ros-args --params-file config/params.yaml
ros2 run vision_io lip_activity_detector --ros-args --params-file config/lip_activity_params.yaml
```

A camera publishing on the configured image topic must be running.

## Configuration

Emotion node parameters live in [`config/params.yaml`](config/params.yaml) and lip-detector
parameters in [`config/lip_activity_params.yaml`](config/lip_activity_params.yaml). See
[../docs/configuration.md](../docs/configuration.md).
