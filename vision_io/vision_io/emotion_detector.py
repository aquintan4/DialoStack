"""
EmotionDetector — ROS2 node for facial emotion recognition from a camera feed.

Detects the largest visible face with MediaPipe, classifies its emotion with a
Hugging Face image-classification pipeline, and publishes the result as JSON.

Topics published:
  /user_emotion   (String) — JSON {"emotion", "confidence", "source"}.

Topics consumed:
  /camera/image_raw  (sensor_msgs/Image)
"""

import json
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from transformers import pipeline
from PIL import Image as PILImage
import mediapipe as mp
from mediapipe.python.solutions import face_detection as mp_face_detection

# ==== EMOTION DETECTOR NODE ====


class EmotionDetector(Node):
    def __init__(self):
        super().__init__("emotion_detector")

        # Configurable parameters (defaults match the current behavior).
        self.declare_parameter("input_topic", "/camera/image_raw")
        self.declare_parameter("output_topic", "/user_emotion")
        self.declare_parameter("model_name", "dima806/face_emotions_image_detection")
        self.declare_parameter("show_visualization", True)

        input_topic = self.get_parameter("input_topic").value
        output_topic = self.get_parameter("output_topic").value
        model_name = self.get_parameter("model_name").value
        self.show_visualization = self.get_parameter("show_visualization").value

        # Close any leftover windows from a previous run.
        if self.show_visualization:
            cv2.destroyAllWindows()
            cv2.namedWindow("Emotion Detector", cv2.WINDOW_AUTOSIZE)

        self.bridge = CvBridge()
        self.classifier = pipeline("image-classification", model=model_name, device=-1)

        self.face_detector = mp_face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        )

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1
        )

        self.image_sub = self.create_subscription(Image, input_topic, self.image_callback, qos)
        self.emotion_pub = self.create_publisher(String, output_topic, 10)

        self.last_emotion = "Starting..."
        self.processing_lock = threading.Lock()

        self.get_logger().info(
            f"EmotionDetector: {input_topic} -> {output_topic} (model={model_name})"
        )

    # ==== IMAGE CALLBACK ====

    def image_callback(self, msg):
        try:
            # Capture the frame and make a fully independent copy to draw on.
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            canvas = frame.copy()

            rgb_img = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_img)

            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    h, w, _ = canvas.shape

                    x = max(0, int(bbox.xmin * w))
                    y = max(0, int(bbox.ymin * h))
                    width = int(bbox.width * w)
                    height = int(bbox.height * h)

                    # Draw on the clean canvas.
                    if self.show_visualization:
                        cv2.rectangle(canvas, (x, y), (x + width, y + height), (0, 255, 0), 2)

                    if not self.processing_lock.locked():
                        thread = threading.Thread(
                            target=self.classify_emotion, args=(rgb_img.copy(), x, y, width, height)
                        )
                        thread.start()

                    if self.show_visualization:
                        cv2.putText(
                            canvas,
                            self.last_emotion,
                            (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 255, 0),
                            2,
                        )

            # Single draw call per frame.
            if self.show_visualization:
                cv2.imshow("Emotion Detector", canvas)
                cv2.waitKey(1)

        except Exception as e:
            self.get_logger().error(f"Callback error: {e}")

    # ==== EMOTION CLASSIFICATION ====

    def classify_emotion(self, rgb_img, x, y, w, h):
        if self.processing_lock.acquire(blocking=False):
            try:
                face = rgb_img[y : y + h, x : x + w]
                if face.size > 0:
                    face_resized = cv2.resize(face, (224, 224))
                    pil_img = PILImage.fromarray(face_resized)
                    prediction = self.classifier(pil_img)
                    if prediction:
                        emotion = prediction[0]["label"].lower()
                        confidence = float(prediction[0]["score"])
                        self.last_emotion = f"{emotion} ({confidence:.2f})"
                        # JSON format expected by DialogManagerNode on /user_emotion.
                        payload = json.dumps(
                            {
                                "emotion": emotion,
                                "confidence": round(confidence, 3),
                                "source": "vision",
                            }
                        )
                        self.emotion_pub.publish(String(data=payload))
            finally:
                self.processing_lock.release()


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = EmotionDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()
